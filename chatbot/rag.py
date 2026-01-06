# chatbot/rag.py

import os
import numpy as np
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# =======================
# ENV & DB SETUP
# =======================

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL not set")

engine = create_engine(DATABASE_URL)

# =======================
# FEATURE FLAG
# =======================

# IMPORTANT:
# ENABLE_RAG=false  → Render / low-memory
# ENABLE_RAG=true   → Local / demo / judge
ENABLE_RAG = os.getenv("ENABLE_RAG", "false").lower() == "true"

# =======================
# LAZY MODEL HOLDER
# =======================

_model = None

def get_model():
    """
    Lazy-load sentence transformer ONLY when RAG is enabled.
    """
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer("paraphrase-MiniLM-L3-v2")
    return _model

# =======================
# CONFIG
# =======================

TOP_K = 3
SIM_THRESHOLD = 0.55

# =======================
# UTILS
# =======================

def normalize(v: np.ndarray) -> np.ndarray:
    norm = np.linalg.norm(v)
    return v if norm == 0 else v / norm

def parse_embedding(emb_str: str) -> np.ndarray:
    return normalize(
        np.array([float(x) for x in emb_str.split(",")])
    )

# =======================
# MAIN RAG FUNCTION
# =======================

def fetch_policy_context(query: str) -> str | None:
    """
    Returns relevant policy chunks or None.
    SAFE FOR RENDER.
    """

    # 🚨 HARD STOP FOR LOW-MEMORY DEPLOYMENTS
    if not ENABLE_RAG:
        return None

    if not query or not query.strip():
        return None

    # Lazy-load model
    model = get_model()
    query_emb = normalize(model.encode(query))

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
    return "\n\n".join(chunk for _, chunk in scored[:TOP_K])
