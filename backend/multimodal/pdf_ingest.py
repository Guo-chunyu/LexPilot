"""PDF ingestion - extract text, chunk, add to vector DB."""
import os, re, uuid
from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma
from backend.config import EMBED_MODEL_NAME, EMBED_DEVICE, CHROMA_DIR


def extract_pdf_text(file_path: str) -> str:
    """Extract text from PDF. Tries pdfplumber (best CJK) first, then PyMuPDF, then PyPDF2."""
    # Method 1: pdfplumber (best Chinese text support)
    try:
        import pdfplumber
        text_parts = []
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    text_parts.append(t)
        if text_parts:
            return "\n\n".join(text_parts)
    except ImportError:
        pass
    # Method 2: PyMuPDF
    try:
        import fitz
        doc = fitz.open(file_path)
        text_parts = []
        for page in doc:
            text_parts.append(page.get_text())
        doc.close()
        result = "\n\n".join(text_parts)
        # Detect if result is garbled (too many replacement chars)
        if result.count('�') < len(result) * 0.1:
            return result
    except ImportError:
        pass
    # Method 3: PyPDF2
    try:
        from PyPDF2 import PdfReader
        reader = PdfReader(file_path)
        text_parts = []
        for page in reader.pages:
            t = page.extract_text()
            if t:
                text_parts.append(t)
        return "\n\n".join(text_parts)
    except ImportError:
        pass
    raise ImportError("Need pdfplumber, pymupdf, or PyPDF2. Run: pip install pdfplumber")


def chunk_pdf_text(text: str, chunk_size: int = 500, overlap: int = 100) -> list[str]:
    """Split PDF text into overlapping chunks at paragraph boundaries."""
    paragraphs = [p.strip() for p in text.split("\n") if len(p.strip()) > 20]
    chunks = []
    current = ""
    for para in paragraphs:
        if len(current) + len(para) <= chunk_size:
            current += para + "\n"
        else:
            if current.strip():
                chunks.append(current.strip())
            current = para[-overlap:] + "\n" + para + "\n" if len(para) > overlap else para + "\n"
    if current.strip():
        chunks.append(current.strip())
    return chunks if chunks else [text[:chunk_size]]


def ingest_pdf_to_vectordb(file_path: str) -> int:
    """Extract PDF, chunk, and add to existing ChromaDB. Returns number of chunks."""
    fname = os.path.basename(file_path)
    print(f"[PDF] Extracting: {fname}")
    text = extract_pdf_text(file_path)
    if not text.strip():
        print("[PDF] No text extracted")
        return 0

    chunks = chunk_pdf_text(text)
    print(f"[PDF] {len(chunks)} chunks from {fname}")

    documents = []
    for c in chunks:
        documents.append(Document(
            page_content=c,
            metadata={
                "type": "user_document",
                "source": fname,
                "parent_content": c,
                "article_num": "",
            },
        ))

    embeddings = HuggingFaceEmbeddings(model_name=EMBED_MODEL_NAME, model_kwargs={"device": EMBED_DEVICE})
    vectorstore = Chroma(persist_directory=CHROMA_DIR, embedding_function=embeddings)
    uuids = [str(uuid.uuid4()) for _ in documents]
    vectorstore.add_documents(documents, ids=uuids)
    print(f"[PDF] Added {len(documents)} chunks to vector DB")
    return len(documents)
