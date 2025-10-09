import os
from sqlalchemy import create_engine, Table, Column, Integer, String, Numeric, Date, MetaData
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")  # This should be set in Render's environment

# Connect to the database
engine = create_engine(DATABASE_URL)
metadata = MetaData()

# Define customers table
customers = Table(
    'customers', metadata,
    Column('id', Integer, primary_key=True),
    Column('name', String, nullable=False),
    Column('phone', String, unique=True, nullable=False),
    Column('emi_amount', Numeric),
    Column('due_date', Date),
    Column('payment_status', String, default='Pending'),
    Column('last_call_status', String)
)

# Create table if it doesn't exist
metadata.create_all(engine)

print(f"✅ Database and table 'customers' created successfully in {DATABASE_URL}")
