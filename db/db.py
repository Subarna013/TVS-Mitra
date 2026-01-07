import os
from sqlalchemy import create_engine, MetaData, Table, select
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL)
metadata = MetaData()
metadata.reflect(bind=engine)

customers = metadata.tables.get("customers")

def get_customer(phone):
    if not phone or not customers:
        return None

    with engine.connect() as conn:
        row = (
            conn.execute(
                select(customers).where(customers.c.phone == phone)
            )
            .mappings()
            .fetchone()
        )
    return row
