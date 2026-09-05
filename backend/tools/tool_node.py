"""
Function Calling / ReAct Tool Node - LLM can autonomously call tools.
Integrated into LangGraph after the Judge node.
"""
import json
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage, ToolMessage
from langchain_openai import ChatOpenAI
from backend.config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL
from backend.tools.legal_tools import create_legal_registry

TOOL_SYSTEM_PROMPT = """You are a legal AI assistant with access to tools.
Decide if a tool is needed for this query.

Available tools:
1. calculate_equity - Calculate equity value. my_percent=% you own(e.g.40), sell_fraction=portion to sell(0.5=half), valuation=company total in yuan(e.g.10000000 for 1000万)
2. generate_legal_document - Generate a legal document (doc_type, facts)
3. check_law_validity - Verify if a statute is currently valid (law_ref)
4. calculate_labor_compensation - Deterministic N/N+1/2N/unsigned-contract calculation

If a tool IS needed, output ONLY: CALL:tool_name:key=value,key=value
Example: CALL:calculate_equity:my_percent=40,sell_fraction=0.5,valuation=10000000

If NO tool is needed, output ONLY: NONE

User query: {query}
Context: {context_summary}
"""


def tool_decider_node(state: dict, llm: ChatOpenAI | None = None) -> dict:
    """
    Decides whether to invoke tools based on the user query.
    Runs after Judge, before final output.
    """
    # Only for LEGAL queries that have completed the main pipeline
    if state.get("intent") != "LEGAL":
        return {"tool_results": "", "tools_used": []}

    query = state["messages"][-1].content if state.get("messages") else ""
    context = state.get("context", [])

    # Check for tool triggers first (before any short-circuit)
    needs_tool = False
    tool_hints = []

    if any(k in query for k in ["持股", "估值", "计算", "多少钱", "转让价", "百分之", "一半能卖", "值多少"]):
        tool_hints.append("calculate_equity")
        needs_tool = True
    if any(k in query for k in ["起草", "生成", "写一份", "模板", "协议", "帮我", "合同", "章程", "卖股份", "转让协议"]):
        tool_hints.append("generate_legal_document")
        needs_tool = True
    if any(k in query for k in ["最新", "2024", "2025", "2026", "修订", "是否有效", "废止"]):
        tool_hints.append("check_law_validity")
        needs_tool = True

    if not needs_tool:
        return {"tool_results": "", "tools_used": []}

    # LLM decides which tool
    if llm is None:
        llm = ChatOpenAI(model=DEEPSEEK_MODEL, api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL, temperature=0)

    context_summary = "\n".join(context[:2]) if context else "no context"
    prompt = TOOL_SYSTEM_PROMPT.format(query=query, context_summary=context_summary[:500])

    try:
        resp = llm.invoke([HumanMessage(content=prompt)])
        raw = resp.content.strip()
    except Exception:
        return {"tool_results": "", "tools_used": []}

    if not raw.upper().startswith("CALL:"):
        return {"tool_results": "", "tools_used": []}

    # Parse: CALL:tool_name:key=value,key=value
    try:
        parts = raw[5:].strip().split(":")
        tool_name = parts[0].strip()
        args = {}
        for kv in parts[1].split(","):
            k, v = kv.split("=")
            k, v = k.strip(), v.strip()
            # Convert numeric values
            try: v = float(v); v = int(v) if v == int(v) else v
            except: pass
            args[k] = v

        registry = create_legal_registry()
        if tool_name in registry.get_tool_names():
            result = registry.execute(tool_name, args)
            result_str = json.dumps(result, ensure_ascii=False, indent=2)
            print(f"[Tool] {tool_name} -> {result_str[:100]}")
            return {"tool_results": f"[Tool: {tool_name}]\n{result_str}", "tools_used": [tool_name]}
    except Exception as e:
        print(f"[Tool] Parse error: {e}")

    return {"tool_results": "", "tools_used": []}
