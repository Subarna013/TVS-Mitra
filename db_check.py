# db_check.py
from sqlalchemy import create_engine, MetaData, select
from dotenv import load_dotenv
import os

# ------------------ LOAD ENV ------------------
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError("❌ DATABASE_URL not set in environment variables")

# ------------------ DB SETUP ------------------
engine = create_engine(DATABASE_URL)
metadata = MetaData()
metadata.reflect(bind=engine)

# ------------------ VALIDATION ------------------
if "customers" not in metadata.tables:
    raise RuntimeError("❌ 'customers' table not found!")

customers = metadata.tables["customers"]
call_logs = metadata.tables.get("call_logs")
policy_chunks = metadata.tables.get("policy_chunks")

# ------------------ QUERIES ------------------
with engine.connect() as conn:

    print("=== CUSTOMERS ===")
    results = conn.execute(
        select(
            customers.c.id,
            customers.c.name,
            customers.c.phone,
            customers.c.payment_status,
            customers.c.due_date,
            customers.c.last_call_date,
            customers.c.last_call_status,
        ).order_by(customers.c.id.asc())
    ).fetchall()

    if not results:
        print("No customers found.")
    else:
        for row in results:
            print(
                f"ID={row.id}, Name={row.name}, Phone={row.phone}, "
                f"Status={row.payment_status}, DueDate={row.due_date}, "
                f"LastCallDate={row.last_call_date}, LastStatus={row.last_call_status}"
            )

    print("\n=== RECENT CALL LOGS (last 20) ===")

    if call_logs is None:
        print("ℹ️ 'call_logs' table does not exist yet.")
    else:
        logs = conn.execute(
            select(
                call_logs.c.id,
                call_logs.c.customer_id,
                call_logs.c.phone,
                call_logs.c.action,
                call_logs.c.outcome,
                call_logs.c.payment_link,
                call_logs.c.created_at,
            )
            .order_by(call_logs.c.created_at.desc())
            .limit(20)
        ).fetchall()

        if not logs:
            print("No call logs found.")
        else:
            for row in logs:
                print(
                    f"LogID={row.id}, CustID={row.customer_id}, Phone={row.phone}, "
                    f"Action={row.action}, Outcome={row.outcome}, "
                    f"Link={row.payment_link}, Time={row.created_at}"
                )

    print("\n=== POLICY CHUNKS ===")
    if not policy_chunks:
        print("ℹ️ 'policy_chunks' table does not exist.")
    else:
        count = conn.execute(
            select(policy_chunks.c.id)
        ).fetchall()
        print(f"Total policy chunks: {len(count)}")
