"""Incremental summarizer - maintains case memo, triggers every 4 turns."""
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from backend.config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL

SUMMARIZER_PROMPT = """# ROLE: Legal Case Memo Keeper
Maintain concise long-term memory.
Format: 1.Core Facts 2.Disputes 3.User Goals 4.Stage. Max 150 chars. Facts only, no analysis."""

def summarize_node(state: dict, llm: ChatOpenAI | None = None) -> dict:
    if llm is None:
        llm = ChatOpenAI(model=DEEPSEEK_MODEL, api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL, temperature=0)
    messages = state["messages"]
    existing = state.get("summary", "")
    if len(messages) <= 2 and not existing:
        return {"summary": "No memo yet"}
    if len(messages) % 4 != 0 and existing:
        return {"summary": existing}
    recent = messages[-4:]
    try:
        res = llm.invoke([SystemMessage(content=SUMMARIZER_PROMPT), HumanMessage(content=f"Existing: {existing}\nNew: {recent}")], max_tokens=200).content
        return {"summary": res}
    except Exception:
        return {"summary": existing or "Summary unavailable"}
