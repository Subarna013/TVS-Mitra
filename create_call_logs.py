from sqlalchemy import (
    create_engine,
    MetaData,
    Table,
    Column,
    Integer,
    String,
    DateTime,
    ForeignKey,
    func,
)
from dotenv import load_dotenv
import os

# ------------------ LOAD ENV ------------------
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError("❌ DATABASE_URL is not set in environment variables")

# ------------------ DB SETUP ------------------
engine = create_engine(DATABASE_URL)
metadata = MetaData()

# Reflect existing tables so we can attach FK to customers.id
metadata.reflect(bind=engine)

if "customers" not in metadata.tables:
    print("❌ Could not find a table named 'customers'. Existing tables are:")
    print(list(metadata.tables.keys()))
else:
    # If call_logs already exists, don't recreate – just inform
    if "call_logs" in metadata.tables:
        print("ℹ️ 'call_logs' table already exists. No changes made.")
    else:
        call_logs = Table(
            "call_logs",
            metadata,
            Column("id", Integer, primary_key=True),
            Column("customer_id", Integer, ForeignKey("customers.id"), nullable=True),
            Column("phone", String(20), nullable=False),
            Column("action", String(100), nullable=False),
            Column("outcome", String(100), nullable=False),
            Column("payment_link", String(255)),
            Column("created_at", DateTime, server_default=func.now()),
        )

        metadata.create_all(engine)
        print("✅ 'call_logs' table created successfully!")
