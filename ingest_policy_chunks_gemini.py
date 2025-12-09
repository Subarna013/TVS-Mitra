import os
import json
import logging
from dotenv import load_dotenv
from sqlalchemy import create_engine, MetaData, Table, insert
import google.generativeai as genai

load_dotenv()
logging.basicConfig(level=logging.INFO)

DATABASE_URL = os.getenv("DATABASE_URL")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL not set")

if not GEMINI_API_KEY:
    raise RuntimeError("GEMINI_API_KEY not set")

genai.configure(api_key=GEMINI_API_KEY)

engine = create_engine(DATABASE_URL)
metadata = MetaData()
metadata.reflect(bind=engine)

if "policy_chunks" not in metadata.tables:
    raise RuntimeError("policy_chunks table not found")

policy_chunks = Table("policy_chunks", metadata, autoload_with=engine)


def embed_text(text: str):
    """Get embedding from Gemini (text-embedding-004)."""
    resp = genai.embed_content(
        model="models/text-embedding-004",
        content=text,
    )
    return resp["embedding"]  # list[float]


def chunk_text(text: str, max_len: int = 500):
    """Basic sentence-based chunking."""
    sentences = text.split(".")
    chunks = []
    current = ""

    for s in sentences:
        s = s.strip()
        if not s:
            continue

        # +1 for the dot/space
        if len(current) + len(s) + 1 <= max_len:
            if current:
                current += ". " + s
            else:
                current = s
        else:
            chunks.append(current)
            current = s

    if current:
        chunks.append(current)

    return chunks


def main():
    # 1) Load JSON
    with open("policy_source.json", "r", encoding="utf-8") as f:
        rows = json.load(f)

    with engine.begin() as conn:
        for row in rows:
            doc_name = row.get("doc_name", "unknown_doc")
            section = row.get("section", "general")
            text = (row.get("text") or "").strip()

            if not text:
                continue

            # 2) Split into smaller chunks
            chunks = chunk_text(text)

            for ch in chunks:
                logging.info(f"👉 Embedding chunk: {doc_name}/{section}: {ch[:80]}...")
                emb = embed_text(ch)  # list of floats
                emb_str = ",".join(str(x) for x in emb)

                stmt = insert(policy_chunks).values(
                    doc_name=doc_name,
                    section=section,
                    chunk_text=ch,
                    embedding=emb_str,
                )
                conn.execute(stmt)

    logging.info("✅ Finished ingesting policy chunks.")


if __name__ == "__main__":
    main()
