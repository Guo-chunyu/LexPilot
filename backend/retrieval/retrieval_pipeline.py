"""Retrieval pipeline - unified entry: multi-source + RRF + two-stage rerank."""
import re
from datetime import date
from typing import List, Optional
from langchain_core.documents import Document
from langchain_openai import ChatOpenAI
from backend.config import (
    VECTOR_K, BM25_K, RERANK_CANDIDATE_K, RERANK_FINAL_K,
    MULTI_QUERY_MIN_SCORE, MULTI_QUERY_VARIANTS,
    DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL,
)
from backend.retrieval.rrf import rrf_fusion, jaccard_similarity
from backend.retrieval.multi_query import generate_query_variants


class RetrievalPipeline:
    """Multi-source retrieval with RRF fusion and two-stage rerank."""

    def __init__(self, vector_retriever, bm25_retriever, reranker, llm=None):
        self.vector_retriever = vector_retriever
        self.bm25_retriever = bm25_retriever
        self.reranker = reranker
        self.llm = llm
        self._last_query = ""

    def retrieve(self, query: str, top_k: int = RERANK_FINAL_K,
                 enable_multi_query: bool = True,
                 include_user_docs: bool = False,
                 event_date: date | str | None = None) -> List[Document]:
        self._last_query = query

        # Stage 1: Multi-source recall
        vector_docs = self._safe_retrieve(self.vector_retriever, query, VECTOR_K)
        bm25_docs = self._safe_retrieve(self.bm25_retriever, query, BM25_K)

        # Filter out user docs by default
        if not include_user_docs:
            vector_docs = [d for d in vector_docs if d.metadata.get("type") != "user_document"]
            bm25_docs = [d for d in bm25_docs if d.metadata.get("type") != "user_document"]

        # Stage 2: RRF fusion
        candidates = rrf_fusion([vector_docs, bm25_docs])
        # Stage 3: Multi-Query expansion if recall is low
        if enable_multi_query and self._should_expand(candidates):
            extra = self._multi_query_retrieve(query)
            candidates = rrf_fusion([candidates, extra])

        if event_date:
            candidates = [doc for doc in candidates if _effective_on(doc, event_date)]

        if not candidates:
            return []

        # Stage 4: Two-stage rerank
        return self._two_stage_rerank(query, candidates, top_k)

    def _safe_retrieve(self, retriever, query: str, k: int) -> List[Document]:
        try:
            return retriever.invoke(query)[:k]
        except Exception as e:
            print(f"  [!] Retrieve error: {e}")
            return []

    def _should_expand(self, candidates: List[Document]) -> bool:
        if len(candidates) < 3:
            return True
        if len(candidates) >= 3 and self._last_query:
            scores = [jaccard_similarity(self._last_query, d.page_content)
                      for d in candidates[:3]]
            return sum(scores) / len(scores) < MULTI_QUERY_MIN_SCORE
        return False

    def _multi_query_retrieve(self, query: str) -> List[Document]:
        if self.llm is None:
            self.llm = ChatOpenAI(
                model=DEEPSEEK_MODEL, api_key=DEEPSEEK_API_KEY,
                base_url=DEEPSEEK_BASE_URL, temperature=0,
            )
        variants = generate_query_variants(query, self.llm, MULTI_QUERY_VARIANTS)
        all_docs = []
        for q in variants:
            all_docs.extend(self._safe_retrieve(self.vector_retriever, q, VECTOR_K))
            all_docs.extend(self._safe_retrieve(self.bm25_retriever, q, BM25_K))
        return all_docs

    def _two_stage_rerank(self, query: str, candidates: List[Document],
                          top_k: int) -> List[Document]:
        # Stage A: Jaccard keyword coarse filter
        scored = [(jaccard_similarity(query, d.page_content), d)
                  for d in candidates]
        scored.sort(key=lambda x: x[0], reverse=True)
        top_n = scored[:RERANK_CANDIDATE_K]

        if len(top_n) <= top_k:
            return [doc for _, doc in top_n]

        # Stage B: Cross-Encoder fine rerank
        try:
            pairs = [[query, doc.page_content] for _, doc in top_n]
            ce_scores = self.reranker.predict(pairs)
            ranked = sorted(zip(ce_scores, [doc for _, doc in top_n]),
                            key=lambda x: x[0], reverse=True)
            return [doc for _, doc in ranked[:top_k]]
        except Exception as e:
            print(f"  [!] Reranker error: {e}")
            return [doc for _, doc in top_n[:top_k]]


def extract_article_num(text: str) -> Optional[str]:
    m = re.search(r"第([一二三四五六七八九十百千]+)条", text)
    return m.group(0) if m else None


def format_context(docs: List[Document]) -> str:
    parts = []
    for i, doc in enumerate(docs, 1):
        src = doc.metadata.get("source", "unknown")
        art = extract_article_num(doc.page_content)
        header = f"[Chunk {i}] {art or 'Statute'} (source: {src})"
        parts.append(f"{header}\n{doc.page_content}")
    return "\n\n---\n\n".join(parts)


def _effective_on(doc: Document, event_date: date | str) -> bool:
    """Temporal filter for documents that carry effective_from/effective_to metadata."""
    when = date.fromisoformat(event_date) if isinstance(event_date, str) else event_date
    start_raw = doc.metadata.get("effective_from")
    end_raw = doc.metadata.get("effective_to")
    start = date.fromisoformat(str(start_raw)) if start_raw else None
    end = date.fromisoformat(str(end_raw)) if end_raw else None
    return not ((start and when < start) or (end and when > end))
