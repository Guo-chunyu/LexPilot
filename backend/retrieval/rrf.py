"""RRF (Reciprocal Rank Fusion) - multi-source retrieval fusion."""
from typing import List
from langchain_core.documents import Document
import re

def jaccard_similarity(query: str, text: str) -> float:
    tokens_q = set(re.findall(r"[一-鿿]{2,}", query))
    tokens_t = set(re.findall(r"[一-鿿]{2,}", text))
    if not tokens_q:
        return 0.5
    intersection = tokens_q & tokens_t
    union = tokens_q | tokens_t
    return len(intersection) / len(union) if union else 0.0

def rrf_fusion(result_groups: List[List[Document]], k: int = 60) -> List[Document]:
    scores: dict = {}
    doc_map: dict = {}
    for results in result_groups:
        for rank, doc in enumerate(results):
            content_key = doc.page_content[:200]
            doc_id = hash(content_key)
            rrf_score = 1.0 / (k + rank + 1)
            scores[doc_id] = scores.get(doc_id, 0) + rrf_score
            if doc_id not in doc_map:
                doc_map[doc_id] = doc
    sorted_ids = sorted(scores.keys(), key=lambda did: scores[did], reverse=True)
    return [doc_map[did] for did in sorted_ids]
