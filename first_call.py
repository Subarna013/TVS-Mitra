import os
from twilio.rest import Client
from dotenv import load_dotenv
from sqlalchemy import create_engine, Table, MetaData, select
from datetime import date

# ------------------ LOAD ENV ------------------
load_dotenv()

account_sid = os.getenv("TWILIO_ACCOUNT_SID")
auth_token = os.getenv("TWILIO_AUTH_TOKEN")
twilio_number = os.getenv("TWILIO_PHONE_NUMBER")
bot_url = os.getenv("BOT_URL")  # e.g., https://tvs-mitra-1.onrender.com

DATABASE_URL = os.getenv("DATABASE_URL")

if not bot_url:
    raise ValueError("Please set BOT_URL in your .env file pointing to /voice endpoint.")

# ------------------ INIT CLIENT ------------------
client = Client(account_sid, auth_token)

# ------------------ DATABASE SETUP ------------------
engine = create_engine(DATABASE_URL)
metadata = MetaData()
customers = Table('customers', metadata, autoload_with=engine)

# ------------------ RISK SCORING ------------------
def calculate_risk_score(customer):
    """Compute risk score for priority calling"""
    score = 0
    if customer.due_date:
        overdue_days = (date.today() - customer.due_date).days
        score += max(overdue_days, 0)
    if customer.emi_amount:
        score += float(customer.emi_amount) / 1000  # weight by EMI amount
    return score

def get_pending_customers_sorted():
    """Fetch pending customers sorted by risk descending"""
    try:
        with engine.connect() as conn:
            query = select(customers).where(customers.c.payment_status == "Pending")
            rows = conn.execute(query).fetchall()
            sorted_customers = sorted(rows, key=calculate_risk_score, reverse=True)
            return sorted_customers
    except Exception:
        print("Error fetching pending customers")
        return []

# ------------------ MAKE CALLS ------------------
def call_customers():
    pending_customers = get_pending_customers_sorted()
    if not pending_customers:
        print("No pending customers to call.")
        return

    for cust in pending_customers:
        # Pre-call verification
        if cust.payment_status == "Paid":
            print(f"Skipping {cust.name}, EMI already paid.")
            continue

        # Ensure phone number format
        phone = cust.phone
        if not phone.startswith("+"):
            phone = "+91" + phone.lstrip("0")

        try:
            call = client.calls.create(
                to=phone,
                from_=twilio_number,
                url=f"{bot_url}/voice"
            )
            print(f"Call initiated to {cust.name} ({phone}) | SID: {call.sid}")
        except Exception as e:
            print(f"Failed to call {cust.name} ({phone}): {str(e)}")

if __name__ == "__main__":
    call_customers()
