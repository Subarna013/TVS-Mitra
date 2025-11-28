import os
from sqlalchemy import (
    create_engine, Table, Column,
    Integer, String, Numeric, Date, DateTime, MetaData
)
from sqlalchemy.sql import func
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError("❌ DATABASE_URL missing in environment variables")

# Connect to the database
engine = create_engine(DATABASE_URL)
metadata = MetaData()

# Define customers table (fully upgraded version)
customers = Table(
    "customers",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String, nullable=False),
    Column("phone", String, unique=True, nullable=False),

    # EMI related
    Column("emi_amount", Numeric, nullable=False),
    Column("due_date", Date),  # used for pre-due and due buckets

    # Payment status
    Column("payment_status", String, default="Pending"),  # Pending / Paid

    # Call intelligence
    Column("last_call_status", String),  # promise_to_pay, link_sent, etc.
    Column("last_call_date", Date),      # used to avoid repeating calls

    # Audit fields
    Column("created_at", DateTime, server_default=func.now()),
    Column("updated_at", DateTime, onupdate=func.now()),
)

# Create tables if not exist
metadata.create_all(engine)

print("✅ Database setup complete! Table 'customers' is ready.")
