"""GraphRAG retrieval - NetworkX in-memory knowledge graph, 1-2 hop expansion."""
import os, json
from typing import List, Optional
import networkx as nx
from langchain_openai import ChatOpenAI
from backend.config import KG_FILE, DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL

ENTITY_EXTRACT_PROMPT = """Extract core Company Law entities from this question.
Entities include: shareholder meeting, board of directors, supervisor, director, LLC, promoter, shareholder, equity, registered capital, bylaws.
Output one entity per line, max 5:

Question: {question}
Entities:"""

class GraphRetriever:
    def __init__(self, kg_path: str = KG_FILE):
        self.G: Optional[nx.DiGraph] = None
        self._llm: Optional[ChatOpenAI] = None
        self._kg_path = kg_path
        self._loaded = False

    def load(self):
        if self._loaded:
            return
        if not os.path.exists(self._kg_path):
            self.G = nx.DiGraph()
            self._loaded = True
            return
        with open(self._kg_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.G = nx.node_link_graph(data)
        self._loaded = True

    @property
    def llm(self) -> ChatOpenAI:
        if self._llm is None:
            self._llm = ChatOpenAI(model=DEEPSEEK_MODEL, api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL, temperature=0)
        return self._llm

    def _extract_entities(self, question: str) -> List[str]:
        try:
            resp = self.llm.invoke(ENTITY_EXTRACT_PROMPT.format(question=question))
            return [e.strip() for e in resp.content.strip().split("\n") if e.strip()][:5]
        except Exception:
            return []

    def search(self, question: str, max_hops: int = 2) -> List[str]:
        self.load()
        if self.G.number_of_nodes() == 0:
            return []
        entities = self._extract_entities(question)
        results, seen = [], set()
        for entity in entities:
            matched = None
            if entity in self.G:
                matched = entity
            else:
                for node in self.G.nodes():
                    if entity in node or node in entity:
                        matched = node
                        break
            if matched is None:
                continue
            for neighbor in self.G.neighbors(matched):
                edge = self.G.get_edge_data(matched, neighbor)
                rel = edge.get("relation", "related")
                key = f"{matched} -> {rel} -> {neighbor}"
                if key not in seen:
                    results.append(key); seen.add(key)
                if max_hops >= 2:
                    for n2 in self.G.neighbors(neighbor):
                        e2 = self.G.get_edge_data(neighbor, n2)
                        r2 = e2.get("relation", "related")
                        key2 = f"  -> {rel} -> {neighbor} -> {r2} -> {n2}"
                        if key2 not in seen:
                            results.append(key2); seen.add(key2)
        return results[:20]

    def format_for_prompt(self, question: str) -> str:
        trails = self.search(question)
        if not trails:
            return ""
        return "\n[Knowledge Graph]:\n" + "\n".join(trails)

graph_retriever = GraphRetriever()
