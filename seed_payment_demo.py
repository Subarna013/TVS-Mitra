# seed_payment_demo.py
from sqlalchemy import create_engine, MetaData, Table, insert
from dotenv import load_dotenv
from datetime import date, timedelta
import os

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError("❌ DATABASE_URL not set")

engine = create_engine(DATABASE_URL)
metadata = MetaData()
metadata.reflect(bind=engine)

if "customers" not in metadata.tables:
    raise RuntimeError("❌ 'customers' table not found")

customers = metadata.tables["customers"]

today = date.today()

demo_rows = [
    # ------- PAID customers -------
    {
        "name": "Demo Paid 1",
        "phone": "+910000000001",
        "emi_amount": 3200,
        "due_date": today - timedelta(days=2),
        "payment_status": "Paid",
        "last_call_status": "promise_to_pay",
    },
    {
        "name": "Demo Paid 2",
        "phone": "+910000000002",
        "emi_amount": 4500,
        "due_date": today - timedelta(days=5),
        "payment_status": "Paid",
        "last_call_status": None,
    },
    {
        "name": "Demo Paid 3",
        "phone": "+910000000003",
        "emi_amount": 2800,
        "due_date": today - timedelta(days=1),
        "payment_status": "Paid",
        "last_call_status": "promise_to_pay",
    },

    # ------- PENDING customers -------
    {
        "name": "Demo Pending 1",
        "phone": "+910000000004",
        "emi_amount": 3000,
        "due_date": today - timedelta(days=3),
        "payment_status": "Pending",
        "last_call_status": None,
    },
    {
        "name": "Demo Pending 2",
        "phone": "+910000000005",
        "emi_amount": 5200,
        "due_date": today + timedelta(days=2),
        "payment_status": "Pending",
        "last_call_status": "promise_to_pay",
    },
    {
        "name": "Demo Pending 3",
        "phone": "+910000000006",
        "emi_amount": 2600,
        "due_date": today + timedelta(days=5),
        "payment_status": "Pending",
        "last_call_status": None,
    },
]

with engine.begin() as conn:
    # avoid duplicate phone constraint
    existing_phones = {
        r[0]
        for r in conn.execute(
            customers.select().with_only_columns(customers.c.phone)
        ).fetchall()
    }

    rows_to_insert = [r for r in demo_rows if r["phone"] not in existing_phones]

    if not rows_to_insert:
        print("ℹ️ No new demo rows to insert (phones already exist).")
    else:
        conn.execute(insert(customers), rows_to_insert)
        print(f"✅ Inserted {len(rows_to_insert)} demo customers.")

print("📌 Done seeding demo data.")
