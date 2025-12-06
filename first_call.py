# first_call.py
import os
from datetime import date, timedelta

from dotenv import load_dotenv
from twilio.rest import Client
from sqlalchemy import create_engine, MetaData, Table, select, update, or_
import razorpay  # Razorpay SDK

# ------------------ LOAD ENV ------------------
load_dotenv()

ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_NUMBER = os.getenv("TWILIO_PHONE_NUMBER")      # for voice calls (normal phone)
BOT_URL = os.getenv("BOT_URL")                        # e.g., https://tvs-mitra-1.onrender.com
DATABASE_URL = os.getenv("DATABASE_URL")

# Twilio WhatsApp Sandbox number
TWILIO_WHATSAPP_NUMBER = "whatsapp:+14155238886"

# Razorpay keys
RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET")

if not BOT_URL:
    raise ValueError("❌ Please set BOT_URL in your .env file pointing to the /voice endpoint.")

if not DATABASE_URL:
    raise RuntimeError("❌ DATABASE_URL not set in environment variables")

if not RAZORPAY_KEY_ID or not RAZORPAY_KEY_SECRET:
    raise RuntimeError("❌ Razorpay keys (RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET) not set in .env")

if not ACCOUNT_SID or not AUTH_TOKEN or not TWILIO_NUMBER:
    raise RuntimeError("❌ Twilio credentials (SID/TOKEN/PHONE) not set in .env")

# ------------------ INIT CLIENTS ------------------
client = Client(ACCOUNT_SID, AUTH_TOKEN)
rzp_client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))

# ------------------ DATABASE SETUP ------------------
engine = create_engine(DATABASE_URL)
metadata = MetaData()
metadata.reflect(bind=engine)

if "customers" not in metadata.tables:
    raise RuntimeError("❌ 'customers' table not found in database")

customers = Table("customers", metadata, autoload_with=engine)


# ------------------ HELPER: NORMALIZE PHONE ------------------
def normalize_phone(phone: str) -> str | None:
    """
    Make sure phone is in +91XXXXXXXXXX format.
    Also handles Twilio WhatsApp format 'whatsapp:+91...'.
    """
    if not phone:
        return None

    phone = phone.strip()

    # Handle Twilio WhatsApp format: "whatsapp:+9190..."
    if phone.startswith("whatsapp:"):
        phone = phone[len("whatsapp:"):]  # remove the prefix

    # Remove spaces and dashes
    phone = phone.replace(" ", "").replace("-", "")

    # Remove leading 0s (e.g. 09123456789 -> 9123456789)
    if phone.startswith("0"):
        phone = phone.lstrip("0")

    # Ensure +91 prefix
    # Ensure +91, but avoid double 91
    if phone.startswith("+"):
        return phone

    # If already looks like 91XXXXXXXXXX, just add +
    if phone.startswith("91") and len(phone) == 12:
        phone = "+" + phone
    else:
        phone = "+91" + phone.lstrip("+")

    return phone



# ------------------ HELPER: CREATE RAZORPAY LINK ------------------
def create_razorpay_payment_link_for_customer(cust):
    """
    Create a Razorpay payment link for this customer and return the URL.
    Does NOT send any SMS/WhatsApp — just returns the link.
    """
    try:
        amount_rupees = float(cust.emi_amount)
        amount_paise = int(round(amount_rupees * 100))

        payload = {
            "amount": amount_paise,
            "currency": "INR",
            "accept_partial": False,
            "description": f"EMI payment for {cust.name}",
            "customer": {
                "name": cust.name,
                "contact": normalize_phone(cust.phone),
                "email": "no-reply@example.com",
            },
            "notify": {"sms": True, "email": False},
            "reminder_enable": True,
        }

        resp = rzp_client.payment_link.create(payload)
        link = resp.get("short_url") or resp.get("shortLink") or resp.get("link")
        print(f"✅ Razorpay link for {cust.name}: {link}")
        return link

    except Exception as e:
        print(f"❌ Failed to create Razorpay link for {cust.name}: {e}")
        return None


# ------------------ HELPER: PLACE A CALL ------------------
def _place_call_to_customer(cust, bucket: str):
    """Place a Twilio call to a single customer row, with pre_due/due bucket."""

    # 0) Skip if already paid
    if getattr(cust, "payment_status", None) == "Paid":
        print(f"⏭️ Skipping {cust.name}, EMI already paid.")
        return

    # 1) Avoid calling more than once per day
    from datetime import date as _date
    if getattr(cust, "last_call_date", None) == _date.today():
        print(f"⏭️ Skipping {cust.name}, already called today.")
        return

    # 2) Normalize phone number (for call + WhatsApp)
    phone = normalize_phone(cust.phone)
    if not phone:
        print(f"⏭️ Skipping {cust.name}, invalid phone.")
        return

    try:
        # 3️⃣ Place the outbound IVR call (normal voice call)
        call = client.calls.create(
            to=phone,
            from_=TWILIO_NUMBER,
            url=f"{BOT_URL}/voice?bucket={bucket}",
        )
        print(
            f"[{bucket.upper()}] 📞 Call initiated to {cust.name} ({phone}) | "
            f"SID: {call.sid}"
        )

        # 4️⃣ Update last_call_date in DB
        with engine.begin() as conn:
            stmt = (
                update(customers)
                .where(customers.c.phone == cust.phone)
                .values(last_call_date=_date.today())
            )
            conn.execute(stmt)

        # 5️⃣ Create payment link
        payment_link = create_razorpay_payment_link_for_customer(cust)
        if not payment_link:
            payment_link = "https://example.com/demo-emi-payment"

        # 6️⃣ Send WhatsApp message with BOTH payment link + chatbot link
        try:
            chat_url = f"{BOT_URL}/chat?phone={phone}"

            wa_body = (
                f"Hello {cust.name}, this is TVS Mitra from TVS Credit.\n"
                "We just tried calling you about your EMI.\n\n"
                "💳 Pay your EMI directly here:\n"
                f"{payment_link}\n\n"
                "💬 You can also chat with our assistant and manage your EMI here:\n"
                f"{chat_url}\n\n"
                "You can type 'pay', 'status', 'why should I pay', or any question in the chat."
            )

            client.messages.create(
                to=f"whatsapp:{phone}",
                from_=TWILIO_WHATSAPP_NUMBER,
                body=wa_body,
            )
            print(f"✉️ WhatsApp (chatbot + payment link) sent to {cust.name} ({phone})")

        except Exception as e:
            print(f"⚠️ Failed to send WhatsApp to {cust.name}: {e}")

    except Exception as e:
        print(f"[{bucket.upper()}] ❌ Failed to call {cust.name} ({phone}): {str(e)}")


# ------------------ MAKE CALLS (SCHEDULER) ------------------
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
        from_=TWILIO_NUMBER,
        url=f"{BOT_URL}/voice?bucket={bucket}",
    )
    print(f"📞 Manual call initiated to {phone}, SID: {call.sid}")


# ------------------ MAIN ------------------
if __name__ == "__main__":
    call_customers()
