# ingest_policies.py
import os
import textwrap
import psycopg2
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv
from pypdf import PdfReader  # or any pdf/text reader

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
model = SentenceTransformer("all-MiniLM-L6-v2")  # light, good enough

def chunk_text(text, max_chars=800):
    # simple splitter, you can improve later
    text = text.replace("\n", " ")
    return textwrap.wrap(text, max_chars)

def store_chunk(cur, doc_name, section, chunk_text, emb):
    cur.execute(
        """
        INSERT INTO policy_chunks (doc_name, section, chunk_text, embedding)
        VALUES (%s, %s, %s, %s)
        """,
        (doc_name, section, chunk_text, emb)
    )

def process_pdf(path):
    reader = PdfReader(path)
    full_text = ""
    for page in reader.pages:
        full_text += page.extract_text() + "\n"

    chunks = chunk_text(full_text)
    embeddings = model.encode(chunks)

    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    for chunk, emb in zip(chunks, embeddings):
        store_chunk(cur, os.path.basename(path), "full_doc", chunk, emb.tolist())
    conn.commit()
    conn.close()

if __name__ == "__main__":
    # put some TVS policy pdfs in ./policies
    for fname in os.listdir("policies"):
        if fname.lower().endswith(".pdf"):
            process_pdf(os.path.join("policies", fname))
            print("Ingested:", fname)
