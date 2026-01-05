# chatbot/ingest/ingest_policies.py

import os
from sqlalchemy import create_engine, text
from sentence_transformers import SentenceTransformer
from chatbot.ingest.chunker import chunk_text
from dotenv import load_dotenv

# =======================
# SETUP
# =======================

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL not set")

engine = create_engine(DATABASE_URL)
model = SentenceTransformer("all-MiniLM-L6-v2")

POLICY_FOLDER = "policy_docs"

# =======================
# INGESTION PIPELINE
# =======================

def ingest():
    if not os.path.isdir(POLICY_FOLDER):
        raise RuntimeError(f"Policy folder not found: {POLICY_FOLDER}")

    for file in os.listdir(POLICY_FOLDER):
        if not file.lower().endswith(".txt"):
            continue

        file_path = os.path.join(POLICY_FOLDER, file)

        with open(file_path, "r", encoding="utf-8") as f:
            text_data = f.read().strip()

        if not text_data:
            continue

        # 1️⃣ Chunking
        chunks = chunk_text(text_data)
        if not chunks:
            continue

        # 2️⃣ Embedding
        embeddings = model.encode(
            chunks,
            normalize_embeddings=True,
            show_progress_bar=False
        )

        # 3️⃣ Atomic DB write
        with engine.begin() as conn:
            # 🔴 Remove old chunks for this document (idempotent ingestion)
            conn.execute(
                text("DELETE FROM policy_chunks WHERE doc_name = :doc"),
                {"doc": file}
            )

            for chunk, emb in zip(chunks, embeddings):
                conn.execute(
                    text("""
                        INSERT INTO policy_chunks
                        (doc_name, chunk_text, embedding)
                        VALUES (:doc, :chunk, :embedding)
                    """),
                    {
                        "doc": file,
                        "chunk": chunk,
                        "embedding": ",".join(map(str, emb.tolist())),
                    }
                )

        print(f"✅ Ingested policy: {file}")

    print("🎉 Policy ingestion complete")


if __name__ == "__main__":
    ingest()
