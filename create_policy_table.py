from sqlalchemy import create_engine, MetaData, Table, Column, Integer, Text
from dotenv import load_dotenv
import os

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError("❌ DATABASE_URL missing")

engine = create_engine(DATABASE_URL)
metadata = MetaData()

policy_chunks = Table(
    "policy_chunks",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("doc_name", Text),
    Column("section", Text),
    Column("chunk_text", Text),
    # 👉 store embedding as comma-separated string
    Column("embedding", Text),
)

metadata.create_all(engine)
print("✅ policy_chunks table created successfully!")
