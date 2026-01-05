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
model = SentenceTransformer("all-MiniLM-L6-v2")

TOP_K = 3
SIM_THRESHOLD = 0.55

# =======================
# UTILS
# =======================

def normalize_vec(v: np.ndarray) -> np.ndarray:
    norm = np.linalg.norm(v)
    return v / norm if norm != 0 else v

def parse_embedding(emb_str: str) -> np.ndarray:
    return normalize_vec(
        np.array([float(x) for x in emb_str.split(",")])
    )

# =======================
# RAG FETCH
# =======================

def fetch_policy_context(query: str) -> str | None:
    """
    Retrieves relevant policy chunks using vector similarity.
    Returns None if no relevant context is found.
    """

    if not query or not query.strip():
        return None

    query_emb = normalize_vec(model.encode(query))

    try:
        with engine.connect() as conn:
            rows = conn.execute(
                text("SELECT chunk_text, embedding FROM policy_chunks")
            ).fetchall()
    except Exception:
        return None

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
    return "\n\n".join(chunk for _, chunk in scored[:TOP_K])
