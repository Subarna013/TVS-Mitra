# chatbot/ingest/ingest_policies.py

import os
from sqlalchemy import create_engine, text
from sentence_transformers import SentenceTransformer
from chatbot.ingest.chunker import chunk_text
from dotenv import load_dotenv


import os
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["NUMEXPR_NUM_THREADS"] = "1"

# =======================
# SETUP
# =======================

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL)

model = SentenceTransformer("paraphrase-MiniLM-L3-v2")

POLICY_FOLDER = "chatbot/policy_docs"


# =======================
# INGESTION
# =======================

def ingest():
    for file in os.listdir(POLICY_FOLDER):
        if not file.endswith(".txt"):
            continue

        path = os.path.join(POLICY_FOLDER, file)

        with open(path, "r", encoding="utf-8") as f:
            text_data = f.read()

        chunks = chunk_text(text_data)
        if not chunks:
            continue

        embeddings = model.encode(
            chunks,
            batch_size=4,
            show_progress_bar=True
        )

        with engine.begin() as conn:
            # 🔴 Prevent duplicates
            conn.execute(
                text("DELETE FROM policy_chunks WHERE doc_name = :doc"),
                {"doc": file}
            )

            for chunk, emb in zip(chunks, embeddings):
                conn.execute(
                    text("""
                        INSERT INTO policy_chunks (doc_name, chunk_text, embedding)
                        VALUES (:doc, :text, :emb)
                    """),
                    {
                        "doc": file,
                        "text": chunk,
                        "emb": ",".join(map(str, emb.tolist()))
                    }
                )

    print("✅ Policy ingestion complete")

if __name__ == "__main__":
    ingest()
