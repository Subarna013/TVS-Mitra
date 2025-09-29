from sqlalchemy import create_engine, Table, Column, Integer, String, Numeric, Date, MetaData

# Use your correct PostgreSQL credentials
engine = create_engine('postgresql://postgres:admin123@localhost:5432/mitra_db')

metadata = MetaData()

customers = Table(
    'customers', metadata,
    Column('id', Integer, primary_key=True),
    Column('name', String),
    Column('phone', String, unique=True),
    Column('emi_amount', Numeric),
    Column('due_date', Date),
    Column('payment_status', String, default='Pending'),
    Column('last_call_status', String)
)

metadata.create_all(engine)

print("Database and table 'customers' created successfully in mitra_db!")
