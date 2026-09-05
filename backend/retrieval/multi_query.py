"""Multi-Query expansion - generates query variants when recall is low."""
from typing import List
from langchain_openai import ChatOpenAI
from backend.config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL

MULTI_QUERY_PROMPT = """Rewrite the following legal question into 3 different phrasings with the same semantic meaning. One per line, no numbering.

Original: {question}

Variants:"""

def generate_query_variants(question: str, llm: ChatOpenAI | None = None, n: int = 3) -> List[str]:
    if llm is None:
        llm = ChatOpenAI(model=DEEPSEEK_MODEL, api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL, temperature=0)
    try:
        resp = llm.invoke(MULTI_QUERY_PROMPT.format(question=question))
        lines = [l.strip() for l in resp.content.strip().split("\n") if l.strip()]
        return [question] + lines[:n]
    except Exception:
        return [question]
