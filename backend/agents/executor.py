"""Executor Agent - aggregates results, generates final response."""
import re
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from langchain_openai import ChatOpenAI
from langchain_core.output_parsers import PydanticOutputParser
from backend.config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL, LLM_TEMPERATURE
from backend.schemas import FinalResponse
from backend.retrieval.retrieval_pipeline import format_context

EXECUTOR_PROMPT = """# ROLE: Senior Legal Advisor
You provide Company Law consultation. For LEGAL queries, answer strictly based on research report.

When [Your Document] is provided in the report:
- Cross-reference the user's document clauses with Company Law provisions
- Flag: compliant items / potential risks / violations
- Cite specific law articles that apply to each clause

Otherwise answer based on the law reference alone.
If report lacks coverage, say so. Do not fabricate.
For document drafting: wrap in <DOC_CONTENT>...</DOC_CONTENT>. Mark with [TRIGGER_DOC: title].
Output strict JSON with reply_text, needs_doc, doc_title, doc_content."""

def executor_node(state: dict, llm: ChatOpenAI | None = None) -> dict:
    if llm is None:
        llm = ChatOpenAI(model=DEEPSEEK_MODEL, api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL, temperature=LLM_TEMPERATURE)
    query = state["messages"][-1].content
    intent = state.get("intent", "CHAT")
    summary = state.get("summary", "")

    if intent == "OUT_OF_SCOPE":
        print("[Executor] Out of scope, refusing")
        return {"messages": [AIMessage(content="Sorry, my knowledge base only covers Company Law. Your question is beyond my professional scope.")], "judge_pass": True}

    parser = PydanticOutputParser(pydantic_object=FinalResponse)
    fmt = parser.get_format_instructions()
    fb = state.get("judge_feedback", "")
    fb_note = f"\n\nPrevious answer rejected by QA. Fix: {fb}" if fb else ""
    sys_msg = SystemMessage(content=f"{EXECUTOR_PROMPT}\n\nMemo: {summary}\n\nFormat: {fmt}")

    if intent == "CHAT":
        prompt = [sys_msg] + state["messages"][-4:-1] + [HumanMessage(content=query + fb_note)]
        ans = llm.invoke(prompt)
        try:
            raw = ans.content.strip()
            if raw.startswith("```"):
                raw = re.sub(r"^```(?:json)?\s*", "", raw)
                raw = re.sub(r"\s*```$", "", raw)
            parsed = parser.invoke(raw)
            return {"messages": [AIMessage(content=parsed.reply_text)], "judge_pass": True}
        except Exception:
            return {"messages": [ans], "judge_pass": True}

    pre = state.get("pre_fetched_docs", [])
    ctx = format_context(pre) if pre else "(no results)"
    e_res = state.get("evidence_results", ["none"])
    s_res = state.get("strategy_results", ["none"])
    e_str = "".join(e_res)
    s_str = "".join(s_res)

    # Include KG trails if available
    kg = state.get("kg_trails", "")
    if kg:
        ctx = kg + "\n\n" + ctx

    # Include user document context if uploaded
    user_doc_ctx = state.get("user_doc_context", "")
    user_doc_name = state.get("user_doc_name", "")
    if user_doc_ctx:
        ctx = f"[Your Document: {user_doc_name}]\n{user_doc_ctx}\n\n---\n{ctx}"

    # Include tool results if any
    tool_results = state.get("tool_results", "")
    if tool_results:
        ctx = f"[Tool Results]\n{tool_results}\n\n---\n{ctx}"

    report = f"[Reference]:\n{ctx}\n\n[Expert]:\n{e_str}\n\n[Strategy]:\n{s_str}"
    prompt = [sys_msg] + state["messages"][-4:-1] + [HumanMessage(content=f"Answer based on report: {query}{fb_note}\n\nReport:\n{report}")]
    ans = llm.invoke(prompt)
    try:
        raw = ans.content.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)
        parsed = parser.invoke(raw)
        ft = parsed.reply_text
        if parsed.needs_doc and parsed.doc_content:
            ft += f"\n\n<DOC_CONTENT>\n{parsed.doc_content.strip()}\n</DOC_CONTENT>\n[TRIGGER_DOC: {parsed.doc_title.strip()}]"
        # Append citations
        if pre:
            ft += "\n\n---\n**References:**"
            for j, d in enumerate(pre[:5]):
                art = d.metadata.get("article_num", ""); src = d.metadata.get("source", "")
                label = art if art else f"source {j+1}"
                snippet = d.page_content[:200].replace("\n", " ")
                ft += f"\n- **{label}** ({src}): {snippet}..."
        print("[Executor] Response complete")
        return {"messages": [AIMessage(content=ft)], "context": [d.page_content for d in pre] if pre else []}
    except Exception as e:
        print(f"[Executor] Fallback: {e}")
        ft = ans.content
        if pre:
            ft += "\n\n---\n**References:**"
            for j, d in enumerate(pre[:5]):
                art = d.metadata.get("article_num", ""); src = d.metadata.get("source", "")
                label = art if art else f"source {j+1}"
                snippet = d.page_content[:200].replace("\n", " ")
                ft += f"\n- **{label}** ({src}): {snippet}..."
        return {"messages": [AIMessage(content=ft)], "context": [d.page_content for d in pre] if pre else []}
