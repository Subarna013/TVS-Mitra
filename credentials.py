from sqlalchemy import create_engine, Table, MetaData, insert
import os
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL)
metadata = MetaData()
metadata.reflect(bind=engine)
customers = Table('customers', metadata, autoload_with=engine)

# Insert test customer
with engine.connect() as conn:
    stmt = insert(customers).values(
        name="Subarna",
        phone="+919064476365",
        emi_amount=3250,
        payment_status="Pending"
    )
    conn.execute(stmt)
    conn.commit()
    print("Test customer added!")
