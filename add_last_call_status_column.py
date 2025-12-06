from sqlalchemy import create_engine, text
from dotenv import load_dotenv
import os

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL)

with engine.begin() as conn:
    conn.execute(
        text(
            "ALTER TABLE customers "
            "ADD COLUMN IF NOT EXISTS last_call_status VARCHAR(255);"
        )
    )

print("✅ Column 'last_call_status' ensured on customers table.")
