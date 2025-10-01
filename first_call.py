import os
from twilio.rest import Client
from dotenv import load_dotenv
from sqlalchemy import create_engine, Table, MetaData, select, update
from datetime import date, datetime

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
    try:
        if customer.due_date:
            due = customer.due_date
            if isinstance(due, str):
                due = datetime.strptime(due, "%Y-%m-%d").date()
            overdue_days = (date.today() - due).days
            score += max(overdue_days, 0)
        if customer.emi_amount:
            score += float(customer.emi_amount) / 1000  # weight by EMI
    except Exception as e:
        print(f"Error calculating risk for {customer.name}: {e}")
    return score

def get_pending_customers_sorted():
    """Fetch pending customers sorted by risk descending"""
    try:
        with engine.connect() as conn:
            query = select(customers).where(customers.c.payment_status == "Pending")
            rows = conn.execute(query).fetchall()
            # Sort by risk score descending
            sorted_customers = sorted(rows, key=calculate_risk_score, reverse=True)
            return sorted_customers
    except Exception as e:
        print(f"Error fetching pending customers: {e}")
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
        if getattr(cust, "last_call_date", None) == date.today():
            print(f"Skipping {cust.name}, already called today.")
            continue

        # Normalize phone number
        phone = cust.phone
        if not phone.startswith("+"):
            phone = "+91" + phone.lstrip("0")
        phone = phone.replace(" ", "").replace("-", "")

        try:
            call = client.calls.create(
                to=phone,
                from_=twilio_number,
                url=f"{bot_url}/voice"
            )
            print(f"Call initiated to {cust.name} ({phone}) | SID: {call.sid}")

            # Update last_call_date in DB
            with engine.begin() as conn:
                stmt = update(customers).where(customers.c.phone == cust.phone).values(last_call_date=date.today())
                conn.execute(stmt)

        except Exception as e:
            print(f"Failed to call {cust.name} ({phone}): {str(e)}")

# ------------------ SINGLE CALL FUNCTION ------------------
def make_call_to_customer(phone_number):
    """Trigger Twilio call to a single customer"""
    call = client.calls.create(
        to=phone_number,
        from_=twilio_number,
        url=f"{bot_url}/voice"
    )
    print(f"Call initiated successfully to {phone_number}, SID: {call.sid}")

# ------------------ MAIN ------------------
if __name__ == "__main__":
    call_customers()
