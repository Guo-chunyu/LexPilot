"""Knowledge graph builder - extract triples from Company Law text."""
import os, re, json, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import networkx as nx
from langchain_openai import ChatOpenAI
from backend.config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL, KG_FILE, LAW_MAIN_FILE

EXTRACT_PROMPT = """Extract legal knowledge triples from this Company Law text.
Format: subject | relation | object
Subjects: shareholder meeting, board of directors, supervisor, LLC, promoter, shareholder, etc.
Relations: elects, removes, limits, exercises, assumes, determines, etc.
Objects: directors, bylaws, registered capital, profit distribution, etc.
One triple per line, max 15. Only extract explicitly stated content.

Text:
{text}

Triples:"""


def split_by_chapter(text):
    chapters = re.split(r"\n(?=第[一二三四五六七八九十]+章)", text)
    return [c.strip() for c in chapters if len(c.strip()) > 100]


def extract_triples(text, llm):
    try:
        resp = llm.invoke(EXTRACT_PROMPT.format(text=text[:2000]))
        lines = resp.content.strip().split("\n")
        triples = []
        for line in lines:
            line = line.strip()
            if "|" in line and not line.startswith("#"):
                parts = line.split("|")
                if len(parts) >= 3:
                    s, r, o = parts[0].strip(), parts[1].strip(), parts[2].strip()
                    if s and r and o and len(s) < 30 and len(r) < 20:
                        triples.append((s, r, o))
        return triples
    except Exception as e:
        print(f"  [!] LLM error: {e}")
        return []


def build():
    if not os.path.exists(LAW_MAIN_FILE):
        print(f"[ERROR] No law text: {LAW_MAIN_FILE}")
        return
    print("[Init] Connecting DeepSeek...")
    llm = ChatOpenAI(model=DEEPSEEK_MODEL, api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL, temperature=0)
    with open(LAW_MAIN_FILE, "r", encoding="utf-8") as f:
        content = f.read()
    chapters = split_by_chapter(content)
    print(f"[Info] {len(chapters)} chapters\n")
    G = nx.DiGraph()
    all_triples = []
    for i, ch in enumerate(chapters):
        title_match = re.search(r"(第[一二三四五六七八九十]+章[^\n]*)", ch)
        title = title_match.group(1) if title_match else f"Chapter {i+1}"
        print(f"  [{i+1}/{len(chapters)}] {title[:40]}")
        triples = extract_triples(ch, llm)
        for s, r, o in triples:
            G.add_edge(s, o, relation=r)
            all_triples.append({"subject": s, "relation": r, "object": o})
        print(f"       -> {len(triples)} triples")
        time.sleep(0.5)

    os.makedirs(os.path.dirname(KG_FILE), exist_ok=True)
    with open(KG_FILE, "w", encoding="utf-8") as f:
        json.dump(nx.node_link_data(G), f, ensure_ascii=False, indent=2)
    print(f"\n[Done] KG saved: {KG_FILE}")
    print(f"   Nodes: {G.number_of_nodes()}, Edges: {G.number_of_edges()}, Triples: {len(all_triples)}")


if __name__ == "__main__":
    build()
