from sqlalchemy import create_engine, Table, MetaData, insert, select
import os
from dotenv import load_dotenv

# ------------------ LOAD ENV ------------------
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

# ------------------ DB SETUP ------------------
engine = create_engine(DATABASE_URL)
metadata = MetaData()
metadata.reflect(bind=engine)
customers = Table('customers', metadata, autoload_with=engine)

# ------------------ INSERT TEST CUSTOMER ------------------
with engine.begin() as conn:  # auto-commit
    # Check if customer already exists
    query = select(customers).where(customers.c.phone == "+919064476365")
    existing = conn.execute(query).fetchone()

    if not existing:
        stmt = insert(customers).values(
            name="Subarna",
            phone="+919064476365",
            emi_amount=3250,
            payment_status="Pending"
        )
        conn.execute(stmt)
        print("✅ Test customer added!")
    else:
        print("ℹ️ Customer already exists, skipping insert.")
