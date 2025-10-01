from sqlalchemy import create_engine, Table, MetaData, update, select
from dotenv import load_dotenv
import os

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL)
metadata = MetaData()
metadata.reflect(bind=engine)
customers = Table('customers', metadata, autoload_with=engine)

phone_to_update = '+919064476365'

# Check before update
with engine.connect() as conn:
    row = conn.execute(select(customers.c.name, customers.c.payment_status)
                       .where(customers.c.phone == phone_to_update)).fetchone()
    print("Before update:", row)

# Update
with engine.begin() as conn:  # ensures commit
    stmt = update(customers).where(customers.c.phone == phone_to_update).values(payment_status='Paid')
    conn.execute(stmt)

# Check after update
with engine.connect() as conn:
    row = conn.execute(select(customers.c.name, customers.c.payment_status)
                       .where(customers.c.phone == phone_to_update)).fetchone()
    print("After update:", row)
