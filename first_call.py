import os
from twilio.rest import Client
from dotenv import load_dotenv
from sqlalchemy import create_engine, Table, MetaData, select, update, or_
from datetime import date, timedelta

# ------------------ LOAD ENV ------------------
load_dotenv()

account_sid = os.getenv("TWILIO_ACCOUNT_SID")
auth_token = os.getenv("TWILIO_AUTH_TOKEN")
twilio_number = os.getenv("TWILIO_PHONE_NUMBER")
bot_url = os.getenv("BOT_URL")        # e.g., https://tvs-mitra-1.onrender.com
DATABASE_URL = os.getenv("DATABASE_URL")

if not bot_url:
    raise ValueError("❌ Please set BOT_URL in your .env file pointing to the /voice endpoint.")

if not DATABASE_URL:
    raise RuntimeError("❌ DATABASE_URL not set in environment variables")

# ------------------ INIT CLIENT ------------------
client = Client(account_sid, auth_token)

# ------------------ DATABASE SETUP ------------------
engine = create_engine(DATABASE_URL)
metadata = MetaData()
customers = Table("customers", metadata, autoload_with=engine)


# ------------------ HELPER: NORMALIZE PHONE ------------------
def normalize_phone(phone: str) -> str:
    if not phone:
        return phone
    phone = phone.strip().replace(" ", "").replace("-", "")
    if phone.startswith("0"):
        phone = phone.lstrip("0")
    if not phone.startswith("+"):
        phone = "+91" + phone
    return phone


# ------------------ HELPER: PLACE A CALL ------------------
def _place_call_to_customer(cust, bucket: str):
    """Place a Twilio call to a single customer row, with pre_due/due bucket."""

    # Pre-call verification
    if getattr(cust, "payment_status", None) == "Paid":
        print(f"⏭️ Skipping {cust.name}, EMI already paid.")
        return

    # Avoid calling more than once per day
    if getattr(cust, "last_call_date", None) == date.today():
        print(f"⏭️ Skipping {cust.name}, already called today.")
        return

    # Normalize phone number
    phone = normalize_phone(cust.phone)
    if not phone:
        print(f"⏭️ Skipping {cust.name}, invalid phone.")
        return

    try:
        # 1️⃣ Place the outbound IVR call
        call = client.calls.create(
            to=phone,
            from_=twilio_number,
            url=f"{bot_url}/voice?bucket={bucket}",
        )
        print(
            f"[{bucket.upper()}] 📞 Call initiated to {cust.name} ({phone}) | "
            f"SID: {call.sid}"
        )

        # 2️⃣ Update last_call_date in DB
        with engine.begin() as conn:
            stmt = (
                update(customers)
                .where(customers.c.phone == cust.phone)
                .values(last_call_date=date.today())
            )
            conn.execute(stmt)

        # 3️⃣ NEW: send chatbot link via SMS (NOT reply-based)
        try:
            chat_url = f"{bot_url}/chat?phone={phone}"
            sms_body = (
                f"Hello {cust.name}, this is TVS Mitra from TVS Credit.\n"
                "We just tried calling you about your EMI.\n"
                "You can chat with our assistant and manage your EMI here:\n"
                f"{chat_url}\n\n"
                "Type 'pay', 'status', 'why should I pay', or any question in the chat."
            )
            client.messages.create(
                to=phone,
                from_=twilio_number,
                body=sms_body,
            )
            print(f"✉️ Chatbot link SMS sent to {cust.name} ({phone})")
        except Exception as e:
            print(f"⚠️ Failed to send chatbot SMS to {cust.name}: {e}")

    except Exception as e:
        print(f"[{bucket.upper()}] ❌ Failed to call {cust.name} ({phone}): {str(e)}")


# ------------------ MAKE CALLS ------------------
def call_customers():
    today = date.today()
    print(f"📅 Running call scheduler for {today}")

    try:
        with engine.connect() as conn:
            # 1) PRE-DUE: EMI due in the next 3 days (but not today)
            pre_due_query = select(customers).where(
                customers.c.payment_status == "Pending",
                customers.c.due_date <= today + timedelta(days=3),
                customers.c.due_date > today,
            )
            pre_due_customers = conn.execute(pre_due_query).fetchall()

            # 2) DUE / OVERDUE:
            #    - EMI due today or earlier
            #    - OR due_date is NULL (treat as DUE so they are not ignored)
            due_query = select(customers).where(
                customers.c.payment_status == "Pending",
                or_(
                    customers.c.due_date <= today,
                    customers.c.due_date.is_(None),
                ),
            )
            due_customers = conn.execute(due_query).fetchall()

    except Exception as e:
        print(f"❌ Error fetching customers: {e}")
        return

    if not pre_due_customers and not due_customers:
        print("ℹ️ No pending customers to call (pre-due or due).")
        return

    # --------- Pass 1: PRE-DUE REMINDERS ----------
    if pre_due_customers:
        print(f"📞 Calling PRE-DUE customers (count = {len(pre_due_customers)})...")
        for cust in pre_due_customers:
            _place_call_to_customer(cust, bucket="pre_due")
    else:
        print("ℹ️ No pre-due customers to call.")

    # --------- Pass 2: DUE / OVERDUE COLLECTIONS ----------
    if due_customers:
        print(f"📞 Calling DUE/OVERDUE customers (count = {len(due_customers)})...")
        for cust in due_customers:
            _place_call_to_customer(cust, bucket="due")
    else:
        print("ℹ️ No due/overdue customers to call.")


# ------------------ SINGLE CALL FUNCTION ------------------
def make_call_to_customer(phone_number, bucket: str = "manual"):
    """Trigger Twilio call to a single customer (manual trigger)."""
    phone = normalize_phone(phone_number)
    call = client.calls.create(
        to=phone,
        from_=twilio_number,
        url=f"{bot_url}/voice?bucket={bucket}",
    )
    print(f"📞 Manual call initiated to {phone}, SID: {call.sid}")


# ------------------ MAIN ------------------
if __name__ == "__main__":
    call_customers()
