"""Evidence Agent - statute lookup."""
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from backend.config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL, LLM_TEMPERATURE

EVIDENCE_PROMPT = """# ROLE: Law researcher
# TASK: Find legal basis in Company Law only.
Rules: Only cite Company Law and its judicial interpretations.
If not found, output [No relevant statute found]. Do not fabricate article numbers."""

def evidence_node(state: dict, llm: ChatOpenAI | None = None) -> dict:
    if llm is None:
        llm = ChatOpenAI(model=DEEPSEEK_MODEL, api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL, temperature=LLM_TEMPERATURE)
    task = state["sub_tasks"][0]
    print(f"[Evidence] Looking up: {task[:60]}...")
    try:
        content = llm.invoke([SystemMessage(content=EVIDENCE_PROMPT), HumanMessage(content=f"Task: {task}")]).content
    except Exception as e:
        content = f"[Search error: {e}]"
    return {"evidence_results": [content]}
