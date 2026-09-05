"""Strategy Agent - practical legal advice."""
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from backend.config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL, LLM_TEMPERATURE

STRATEGY_PROMPT = """# ROLE: Legal Strategy Advisor
# TASK: Give actionable advice based on Company Law only.
Rules: Only base on Company Law. If out of scope, output [Out of scope].
Do not cite specific article numbers. Provide step-by-step guidance."""

DRAFT_KW = ["draft", "generate", "write", "create", "template", "document", "agreement"]

def strategy_node(state: dict, llm: ChatOpenAI | None = None) -> dict:
    if llm is None:
        llm = ChatOpenAI(model=DEEPSEEK_MODEL, api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL, temperature=LLM_TEMPERATURE)
    task = state["sub_tasks"][0]
    print(f"[Strategy] Planning: {task[:60]}...")
    is_draft = any(k in task.lower() for k in DRAFT_KW)
    p = STRATEGY_PROMPT
    if not is_draft:
        p += " Provide advice only. No document templates."
    try:
        content = llm.invoke([SystemMessage(content=p), HumanMessage(content=f"Context: {state.get('summary','')}\nTask: {task}")]).content
    except Exception as e:
        content = f"[Strategy error: {e}]"
    return {"strategy_results": [content]}
