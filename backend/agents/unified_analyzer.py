"""Unified Analyzer - merges Router + Rewriter + Planner into one LLM call."""
import json, re
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from backend.config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL, LLM_TEMPERATURE

UNIFIED_ANALYZER_PROMPT = """# ROLE: Legal AI Dispatcher
Analyze user query and output pure JSON (no markdown, no extra text).

1. intent: user intent
   - "LEGAL" = Company Law, equity, governance, etc.
   - "CHAT" = casual chat, greetings, emotions
   - "OUT_OF_SCOPE" = divorce, inheritance, criminal, labor, etc.

2. rewritten_query: de-referenced search query (LEGAL only, else empty)
   - Replace pronouns, fill in implicit context
   - Translate colloquial terms to formal legal terms:
     "退股/退出公司" -> "股权转让 异议股东回购 减资退股"
     "开除董事" -> "罢免董事 解除董事职务"
     "公司分家" -> "公司分立"
     "公司关门" -> "公司解散 清算"

3. sub_tasks: task breakdown (LEGAL only, max 2, else empty array)
   - [evidence] search Company Law for legal basis
   - [strategy] provide practical advice based on Company Law

Output format example:
{{"intent":"LEGAL","rewritten_query":"What is the shareholder limit for LLCs","sub_tasks":["[evidence] find statute on shareholder count","[strategy] advise on company structure"]}}

Context: {summary}
Question: {query}

JSON:"""

def _extract_json(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start:end + 1]
    return text

def _keyword_fallback(query: str) -> dict:
    legal_kw = ["shareholder", "equity", "director", "supervisor", "bylaw", "capital", "company", "merger", "dissolution", "liquidation", "board", "LLC", "limited liability", "share", "transfer", "article", "incorporation"]
    oos_kw = ["divorce", "inheritance", "will", "marriage", "labor", "wage", "fire", "criminal", "fraud", "theft", "tort", "dog bite", "fight", "neighbor", "tax", "customs"]
    q_lower = query.lower()
    for kw in oos_kw:
        if kw in q_lower:
            return {"intent": "OUT_OF_SCOPE", "rewritten_query": "", "sub_tasks": []}
    for kw in legal_kw:
        if kw in q_lower:
            return {"intent": "LEGAL", "rewritten_query": query, "sub_tasks": [f"[evidence] find Company Law basis for {query}", f"[strategy] give practical advice on {query}"]}
    # Chinese keyword fallback
    cn_legal = ["股东", "股权", "董事", "监事", "章程", "注册资本", "出资", "公司", "合并", "分立", "解散", "清算", "上市", "董事会", "股东会", "法人", "有限责任", "股份", "增资", "减资", "分红", "转让", "设立", "变更"]
    cn_oos = ["离婚", "继承", "遗嘱", "劳动", "工资", "拖欠", "辞退", "开除", "工伤", "社保", "刑事", "犯罪", "盗窃", "诈骗", "侵权", "狗咬", "打架", "邻居", "噪音", "行政", "税务"]
    for kw in cn_oos:
        if kw in query:
            return {"intent": "OUT_OF_SCOPE", "rewritten_query": "", "sub_tasks": []}
    for kw in cn_legal:
        if kw in query:
            return {"intent": "LEGAL", "rewritten_query": query, "sub_tasks": [f"[evidence] find Company Law basis for {query}", f"[strategy] give practical advice on {query}"]}
    return {"intent": "CHAT", "rewritten_query": "", "sub_tasks": []}

def unified_analyzer_node(state: dict, llm: ChatOpenAI | None = None) -> dict:
    if llm is None:
        llm = ChatOpenAI(model=DEEPSEEK_MODEL, api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL, temperature=LLM_TEMPERATURE)
    query = state["messages"][-1].content
    summary = state.get("summary", "")
    try:
        prompt_text = UNIFIED_ANALYZER_PROMPT.format(summary=summary, query=query)
        resp = llm.invoke([HumanMessage(content=prompt_text)])
        json_str = _extract_json(resp.content)
        data = json.loads(json_str)
    except (json.JSONDecodeError, Exception) as e:
        print(f"  [!] JSON parse failed, using keyword fallback: {str(e)[:80]}")
        data = _keyword_fallback(query)
    intent = data.get("intent", "CHAT")
    if intent not in ("LEGAL", "CHAT", "OUT_OF_SCOPE"):
        intent = "CHAT"
    rewritten_query = data.get("rewritten_query", "")
    sub_tasks = data.get("sub_tasks", [])
    if intent in ("CHAT", "OUT_OF_SCOPE"):
        rewritten_query = ""
        sub_tasks = []
    if intent == "LEGAL" and not sub_tasks:
        sub_tasks = [f"[evidence] find Company Law basis for {query}", f"[strategy] give practical advice on {query}"]
    validated_tasks = []
    for t in sub_tasks:
        t = t.strip()
        if "[evidence]" not in t and "[strategy]" not in t:
            t = f"[evidence] {t}"
        validated_tasks.append(t)
    sub_tasks = validated_tasks[:2]
    print(f"--- Analyzer: intent={intent}, tasks={len(sub_tasks)} ---")
    return {"intent": intent, "rewritten_query": rewritten_query, "sub_tasks": sub_tasks}
