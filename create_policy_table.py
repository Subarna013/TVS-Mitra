# create_policy_table.py

import os
from sqlalchemy import create_engine, MetaData, Table, Column, Integer, Text
from dotenv import load_dotenv

# =======================
# LOAD ENV
# =======================

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError("❌ DATABASE_URL missing")

# =======================
# DB SETUP
# =======================

engine = create_engine(DATABASE_URL)
metadata = MetaData()

# =======================
# POLICY CHUNKS TABLE
# =======================

policy_chunks = Table(
    "policy_chunks",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("doc_name", Text, nullable=False),
    Column("chunk_text", Text, nullable=False),
    Column("embedding", Text, nullable=False),  # comma-separated floats
)

metadata.create_all(engine)

print("✅ policy_chunks table created successfully")
