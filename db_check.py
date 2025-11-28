# db_check.py
from sqlalchemy import create_engine, Table, MetaData, select
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

if "customers" not in metadata.tables:
    raise RuntimeError("❌ 'customers' table not found in database!")

customers = Table("customers", metadata, autoload_with=engine)
call_logs = metadata.tables.get("call_logs")  # might not exist yet

# ------------------ QUERIES ------------------
with engine.connect() as conn:
    print("=== CUSTOMERS ===")
    query = select(
        customers.c.id,
        customers.c.name,
        customers.c.phone,
        customers.c.payment_status,
        customers.c.due_date,
        customers.c.last_call_date,
        customers.c.last_call_status,
    ).order_by(customers.c.id.asc())

    results = conn.execute(query).fetchall()
    if not results:
        print("No customers found.")
    else:
        for row in results:
            print(
                f"ID={row.id}, Name={row.name}, Phone={row.phone}, "
                f"Status={row.payment_status}, DueDate={row.due_date}, "
                f"LastCallDate={row.last_call_date}, LastStatus={row.last_call_status}"
            )

    # ----- CALL LOGS -----
    print("\n=== RECENT CALL LOGS (last 20) ===")
    if not call_logs:
        print("ℹ️ 'call_logs' table does not exist yet.")
    else:
        query = (
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
        )

        results = conn.execute(query).fetchall()
        if not results:
            print("No call logs found.")
        else:
            for row in results:
                print(
                    f"LogID={row.id}, CustID={row.customer_id}, Phone={row.phone}, "
                    f"Action={row.action}, Outcome={row.outcome}, "
                    f"Link={row.payment_link}, Time={row.created_at}"
                )
