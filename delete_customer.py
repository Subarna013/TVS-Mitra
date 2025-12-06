from sqlalchemy import create_engine, MetaData, Table, delete
from dotenv import load_dotenv
import os

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL)
metadata = MetaData()
metadata.reflect(bind=engine)
customers = Table('customers', metadata, autoload_with=engine)

phone_to_delete = "+919064476365"   # CHANGE this to the phone you want to delete

with engine.begin() as conn:
    stmt = delete(customers).where(customers.c.phone == phone_to_delete)
    result = conn.execute(stmt)
    print(f"Deleted rows: {result.rowcount}")
