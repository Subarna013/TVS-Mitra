from sqlalchemy import create_engine, MetaData, Table, Column, Integer, String, DateTime, ForeignKey, func
import os
from dotenv import load_dotenv

load_dotenv()
engine = create_engine(os.getenv("DATABASE_URL"))
metadata = MetaData()

# ✅ Reflect existing tables (so foreign keys can see them)
metadata.reflect(bind=engine)

# ✅ Confirm actual customers table name
if "customers" not in metadata.tables:
    print("❌ Could not find a table named 'customers'. Existing tables are:")
    print(metadata.tables.keys())
else:
    call_logs = Table(
        "call_logs",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("customer_id", Integer, ForeignKey("customers.id")),
        Column("phone", String(20)),
        Column("action", String(100)),
        Column("outcome", String(100)),
        Column("payment_link", String(255)),
        Column("created_at", DateTime, server_default=func.now()),
    )

    metadata.create_all(engine)
    print("✅ call_logs table created successfully!")
