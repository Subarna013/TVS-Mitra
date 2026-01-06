# chatbot/rag.py

import os
import numpy as np
from sqlalchemy import create_engine, text
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv

# =======================
# SETUP
# =======================

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

engine = create_engine(DATABASE_URL)
_model = None
ENABLE_RAG = os.getenv("ENABLE_RAG", "false") == "true"

def fetch_policy_context(query):
    if not ENABLE_RAG:
        return None

def get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer("paraphrase-MiniLM-L3-v2")
    return _model

TOP_K = 3
SIM_THRESHOLD = 0.55

# =======================
# UTILS
# =======================

def normalize(v: np.ndarray) -> np.ndarray:
    return v / np.linalg.norm(v)

def parse_embedding(emb_str: str) -> np.ndarray:
    return normalize(np.array([float(x) for x in emb_str.split(",")]))

# =======================
# FETCH CONTEXT
# =======================



    model = get_model()
    query_emb = model.encode(query)

    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT chunk_text, embedding FROM policy_chunks")
        ).fetchall()

    if not rows:
        return None

    scored = []

    for chunk_text, emb_str in rows:
        emb = parse_embedding(emb_str)
        score = float(np.dot(query_emb, emb))

        if score >= SIM_THRESHOLD:
            scored.append((score, chunk_text))

    if not scored:
        return None

    scored.sort(key=lambda x: x[0], reverse=True)
    return "\n\n".join(c for _, c in scored[:TOP_K])
