from sentence_transformers import SentenceTransformer
import psycopg2
from dotenv import load_dotenv
import os

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

EMB_MODEL_NAME = "all-MiniLM-L6-v2"
model = SentenceTransformer(EMB_MODEL_NAME)

# 👇 Example: your policy data – keep whatever you already had
policy_rows = [
    # each row is a dict with these keys:
    # { "doc_name": "...", "section": "...", "chunk_text": "..." }
]

def main():
    print("Connecting to DB...")
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    for row in policy_rows:
        text = row["chunk_text"].strip()
        if not text:
            continue

        print(f"👉 Embedding chunk: {row['doc_name']} / {row['section']}")

        emb = model.encode([text])[0]  # numpy array (384,)
        emb_str = ",".join(f"{x:.6f}" for x in emb.tolist())  # store as CSV string

        cur.execute(
            """
            INSERT INTO policy_chunks (doc_name, section, chunk_text, embedding)
            VALUES (%s, %s, %s, %s)
            """,
            (row["doc_name"], row["section"], text, emb_str),
        )

    conn.commit()
    cur.close()
    conn.close()
    print("✅ Done inserting policy chunks.")

if __name__ == "__main__":
    main()
