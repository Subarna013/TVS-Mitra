from sqlalchemy import create_engine, text
from dotenv import load_dotenv
import os

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("❌ DATABASE_URL not set in environment variables")

engine = create_engine(DATABASE_URL)

with engine.begin() as conn:
    # Add last_call_date column if it doesn't exist
    conn.execute(
        text(
            "ALTER TABLE customers "
            "ADD COLUMN IF NOT EXISTS last_call_date DATE;"
        )
    )

print("✅ Column 'last_call_date' ensured on customers table.")
