import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
from chatbot.ingest.chunker import chunk_text

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
POLICY_FOLDER = "policy_docs"

engine = create_engine(DATABASE_URL)

def ingest():
    # Import ONLY here (critical)
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer("paraphrase-MiniLM-L3-v2")

    for file in os.listdir(POLICY_FOLDER):
        if not file.endswith(".txt"):
            continue

        path = os.path.join(POLICY_FOLDER, file)
        with open(path, "r", encoding="utf-8") as f:
            text_data = f.read()

        chunks = chunk_text(text_data)
        if not chunks:
            continue

        embeddings = model.encode(chunks)

        with engine.begin() as conn:
            # Remove old chunks
            conn.execute(
                text("DELETE FROM policy_chunks WHERE doc_name = :doc"),
                {"doc": file},
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

    print("✅ Policy ingestion completed")

if __name__ == "__main__":
    ingest()
