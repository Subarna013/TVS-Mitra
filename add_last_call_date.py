from sqlalchemy import create_engine, MetaData, Table, update, select
from dotenv import load_dotenv
from datetime import date
import os

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("❌ DATABASE_URL missing in environment variables")

# Connect to DB
engine = create_engine(DATABASE_URL)
metadata = MetaData()
metadata.reflect(bind=engine)

# Get customers table
customers = Table("customers", metadata, autoload_with=engine)

# ------- CHANGE THIS if testing another customer -------
target_phone = "+919064476365"
# --------------------------------------------------------

with engine.begin() as conn:

    # Show BEFORE state
    row = conn.execute(
        select(
            customers.c.id,
            customers.c.name,
            customers.c.phone,
            customers.c.last_call_date,
            customers.c.last_call_status,
            customers.c.payment_status,
            customers.c.due_date
        ).where(customers.c.phone == target_phone)
    ).mappings().fetchone()

    print("\n📌 BEFORE RESET:")
    print(row)

    # Clear last_call_date + last_call_status ONLY (do NOT touch payment_status)
    stmt = (
        update(customers)
        .where(customers.c.phone == target_phone)
        .values(
            last_call_date=None,
            last_call_status=None
        )
    )
    conn.execute(stmt)

    # Show AFTER state
    row = conn.execute(
        select(
            customers.c.id,
            customers.c.name,
            customers.c.phone,
            customers.c.last_call_date,
            customers.c.last_call_status,
            customers.c.payment_status,
            customers.c.due_date
        ).where(customers.c.phone == target_phone)
    ).mappings().fetchone()

    print("\n🔁 AFTER RESET:")
    print(row)

print("\n✅ last_call_date and last_call_status reset successfully!\n")
