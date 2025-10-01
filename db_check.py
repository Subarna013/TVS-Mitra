from sqlalchemy import create_engine, Table, MetaData, select
from dotenv import load_dotenv
import os

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

engine = create_engine(DATABASE_URL)
metadata = MetaData()
metadata.reflect(bind=engine)
customers = Table('customers', metadata, autoload_with=engine)

with engine.connect() as conn:
    query = select(customers.c.name, customers.c.phone, customers.c.payment_status)
    results = conn.execute(query).fetchall()
    for row in results:
        print(row)
