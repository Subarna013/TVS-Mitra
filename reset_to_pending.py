from sqlalchemy import create_engine, Table, MetaData, update, select
from dotenv import load_dotenv
from datetime import date
import os

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("❌ DATABASE_URL not set")

engine = create_engine(DATABASE_URL)
metadata = MetaData()
metadata.reflect(bind=engine)

customers = Table("customers", metadata, autoload_with=engine)

PHONE = "+919064476365"   # your test number

with engine.connect() as conn:
    before = conn.execute(
        select(
            customers.c.id,
            customers.c.name,
            customers.c.phone,
            customers.c.emi_amount,
            customers.c.due_date,
            customers.c.payment_status,
            customers.c.last_call_date,
            customers.c.last_call_status,
        ).where(customers.c.phone == PHONE)
    ).mappings().fetchone()
    print("📌 BEFORE:", before)

# 👉 Reset everything for testing
with engine.begin() as conn:
    stmt = (
        update(customers)
        .where(customers.c.phone == PHONE)
        .values(
            payment_status="Pending",
            due_date=date.today(),      # make it due today
            last_call_date=None,
            last_call_status=None,
        )
    )
    result = conn.execute(stmt)
    print("✅ Rows updated:", result.rowcount)

with engine.connect() as conn:
    after = conn.execute(
        select(
            customers.c.id,
            customers.c.name,
            customers.c.phone,
            customers.c.emi_amount,
            customers.c.due_date,
            customers.c.payment_status,
            customers.c.last_call_date,
            customers.c.last_call_status,
        ).where(customers.c.phone == PHONE)
    ).mappings().fetchone()
    print("📌 AFTER:", after)
