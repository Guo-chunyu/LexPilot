"""Vector DB build - Parent-Child index, no SAC pollution."""
import os, re, sys, shutil
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma
from backend.config import (
    EMBED_MODEL_NAME, EMBED_DEVICE, HF_ENDPOINT, HF_HOME, CHROMA_DIR,
    LAW_MAIN_FILE, LAW_INTERPRET_FILE, LABOR_LAW_SOURCES_FILE,
)

os.environ["HF_ENDPOINT"] = HF_ENDPOINT
os.environ["HF_HOME"] = HF_HOME


def load_and_chunk(file_path, doc_type):
    if not os.path.exists(file_path):
        print(f"[WARN] File not found: {file_path}")
        return []
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
    documents = []
    pattern = re.compile(
        r"(第[一二三四五六七八九十百千]+条[\s\S]*?)(?=\n第[一二三四五六七八九十百千]+条|\Z)",
    )
    matches = pattern.findall(content)
    if matches:
        for match in matches:
            text = match.strip()
            if len(text) < 10:
                continue
            art_num = re.search(r"第[一二三四五六七八九十百千]+条", text)
            documents.append(Document(
                page_content=text,  # Full article text - no summary pollution
                metadata={
                    "type": doc_type,
                    "source": os.path.basename(file_path),
                    "parent_content": text,
                    "article_num": art_num.group(0) if art_num else "",
                },
            ))
    else:
        for p in [p.strip() for p in content.split("\n\n") if len(p.strip()) > 10]:
            documents.append(Document(
                page_content=p,
                metadata={"type": doc_type, "source": os.path.basename(file_path), "parent_content": p, "article_num": ""},
            ))
    print(f"[OK] {os.path.basename(file_path)}: {len(documents)} chunks")
    return documents


def load_labor_sources(file_path):
    """Reuse the existing vector/RRF pipeline for curated labor-law metadata."""
    if not os.path.exists(file_path):
        return []
    import yaml
    with open(file_path, "r", encoding="utf-8") as f:
        sources = yaml.safe_load(f).get("sources", [])
    documents = []
    for item in sources:
        content = f"{item['law_name']} {item['article']}\n{item['summary']}"
        documents.append(Document(
            page_content=content,
            metadata={
                "type": "labor_law",
                "source": item["law_name"],
                "article_num": item["article"],
                "source_url": item["source_url"],
                "effective_from": str(item.get("effective_from") or ""),
                "effective_to": str(item.get("effective_to") or ""),
                "parent_content": content,
            },
        ))
    print(f"[OK] labor law metadata: {len(documents)} chunks")
    return documents


def build():
    if os.path.exists(CHROMA_DIR):
        print(f"[Clean] Removing old: {CHROMA_DIR}")
        shutil.rmtree(CHROMA_DIR)
    print("[Build] Building vector DB (no summary pollution)...")
    all_docs = []
    all_docs += load_and_chunk(LAW_MAIN_FILE, "Company Law")
    all_docs += load_and_chunk(LAW_INTERPRET_FILE, "Judicial Interpretation")
    all_docs += load_labor_sources(LABOR_LAW_SOURCES_FILE)
    if not all_docs:
        print("[ERROR] No legal texts found!")
        return
    print(f"[Total] {len(all_docs)} chunks")
    print("[Embed] Loading BGE...")
    embeddings = HuggingFaceEmbeddings(model_name=EMBED_MODEL_NAME, model_kwargs={"device": EMBED_DEVICE})
    print("[Chroma] Writing...")
    Chroma.from_documents(documents=all_docs, embedding=embeddings, persist_directory=CHROMA_DIR)
    print(f"[Done] Saved to {CHROMA_DIR}")


if __name__ == "__main__":
    build()
