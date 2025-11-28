from sqlalchemy import create_engine, Table, MetaData, insert, select
import os
from dotenv import load_dotenv
from datetime import date

# ------------------ LOAD ENV ------------------
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError("❌ DATABASE_URL not found in environment variables!")

# ------------------ DB SETUP ------------------
engine = create_engine(DATABASE_URL)
metadata = MetaData()
metadata.reflect(bind=engine)

if "customers" not in metadata.tables:
    raise RuntimeError("❌ 'customers' table not found in database!")

customers = metadata.tables["customers"]

# ------------------ CONFIG ------------------
TEST_PHONE = "+919064476365"     # Your number
TEST_DUE_DATE = date.today()     # Or set manually: date(2025, 11, 30)

# ------------------ INSERT TEST CUSTOMER ------------------
with engine.begin() as conn:

    # Show BEFORE state
    before = conn.execute(
        select(customers).where(customers.c.phone == TEST_PHONE)
    ).mappings().fetchone()

    if before:
        print("ℹ️ Customer already exists, skipping insert.")
        print("   Existing record:", before)
    else:
        stmt = insert(customers).values(
            name="Subarna",
            phone=TEST_PHONE,
            emi_amount=3250,
            due_date=TEST_DUE_DATE,
            payment_status="Pending",
            last_call_date=None,
            last_call_status=None
        )
        conn.execute(stmt)
        print("✅ Test customer added!")

    # Show AFTER state
    after = conn.execute(
        select(customers).where(customers.c.phone == TEST_PHONE)
    ).mappings().fetchone()

    print("\n📌 FINAL CUSTOMER RECORD:")
    print(after)
