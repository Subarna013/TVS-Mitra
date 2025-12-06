from sqlalchemy import create_engine, text, MetaData
from dotenv import load_dotenv
import os

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError("❌ DATABASE_URL not set in env")

engine = create_engine(DATABASE_URL)

with engine.begin() as conn:
    # risk_score: numeric between 0 and 1
    conn.execute(
        text(
            "ALTER TABLE customers "
            "ADD COLUMN IF NOT EXISTS risk_score NUMERIC;"
        )
    )

    # risk_bucket: LOW / MEDIUM / HIGH
    conn.execute(
        text(
            "ALTER TABLE customers "
            "ADD COLUMN IF NOT EXISTS risk_bucket VARCHAR(20);"
        )
    )

print("✅ Ensured columns risk_score, risk_bucket exist on customers table.")
