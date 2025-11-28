import os
import logging
from datetime import datetime, date
from flask import Flask, request, Response
from twilio.twiml.voice_response import VoiceResponse, Gather
from twilio.twiml.messaging_response import MessagingResponse
from twilio.rest import Client
from sqlalchemy import create_engine, Table, MetaData, select, update, insert
import razorpay
from dotenv import load_dotenv

# ------------------ SETUP ------------------
load_dotenv()
logging.basicConfig(level=logging.INFO)

# Twilio setup
twilio_sid = os.getenv("TWILIO_ACCOUNT_SID")
twilio_token = os.getenv("TWILIO_AUTH_TOKEN")
twilio_number = os.getenv("TWILIO_PHONE_NUMBER")
twilio_client = Client(twilio_sid, twilio_token)

# Razorpay setup
RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET")
rzp_client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))

# Database setup
DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL)
metadata = MetaData()
metadata.reflect(bind=engine)

# Tables
customers = Table("customers", metadata, autoload_with=engine)
call_logs = Table("call_logs", metadata, autoload_with=engine)

# ------------------ UTILITIES ------------------
def normalize_phone(phone: str):
    if not phone:
        return None
    phone = phone.strip()
    if phone.startswith("0"):
        phone = phone.lstrip("0")
    if not phone.startswith("+"):
        phone = "+91" + phone.lstrip("+")
    return phone

def log_call_entry(phone, action, outcome, payment_link=None, customer_id=None):
    try:
        with engine.begin() as conn:
            conn.execute(
                insert(call_logs).values(
                    customer_id=customer_id,
                    phone=phone,
                    action=action,
                    outcome=outcome,
                    payment_link=payment_link,
                    created_at=datetime.utcnow()
                )
            )
    except Exception:
        logging.exception("Failed to write call log")

def get_customer(phone_number: str):
    """Fetch customer by phone number, return mapping (dict-like)."""
    phone = normalize_phone(phone_number)
    if not phone:
        return None
    try:
        with engine.connect() as conn:
            query = select(customers).where(customers.c.phone == phone)
            row = conn.execute(query).mappings().fetchone()
            logging.info(f"Fetched customer for {phone}: {row}")
            return row
    except Exception:
        logging.exception("Error fetching customer from DB")
        return None

def mark_emi_paid(phone_number: str):
    phone = normalize_phone(phone_number)
    if not phone:
        return False
    try:
        with engine.begin() as conn:
            stmt = update(customers).where(customers.c.phone == phone).values(payment_status="Paid")
            conn.execute(stmt)
            return True
    except Exception:
        logging.exception("Failed to mark paid")
        return False

def create_razorpay_payment_link(customer_name, customer_contact, amount_rupees):
    """Generate Razorpay payment link."""
    try:
        amount_paise = int(round(float(amount_rupees) * 100))
        payload = {
            "amount": amount_paise,
            "currency": "INR",
            "accept_partial": False,
            "description": f"EMI payment for {customer_name}",
            "customer": {"name": customer_name, "contact": customer_contact, "email": "no-reply@example.com"},
            "notify": {"sms": True, "email": False},
            "reminder_enable": True
        }
        resp = rzp_client.payment_link.create(payload)
        link = resp.get("short_url") or resp.get("shortLink")
        logging.info(f"✅ Razorpay link created: {link}")
        return link
    except Exception:
        logging.exception("❌ Failed to create Razorpay link")
        return None


def send_payment_link(customer):
    """Send Razorpay payment link via Twilio SMS (with fallback + phone normalization)."""
    try:
        # ✅ Make sure phone is in +91... format
        phone = normalize_phone(customer["phone"])

        # 1) Try to create Razorpay link
        link = create_razorpay_payment_link(
            customer_name=customer["name"],
            customer_contact=phone,
            amount_rupees=customer["emi_amount"]
        )

        # 2) Fallback link if Razorpay fails
        if not link:
            link = "https://example.com/demo-emi-payment"
            logging.warning("⚠️ Razorpay link failed, using fallback demo link.")

        # 3) Try to send SMS
        msg = twilio_client.messages.create(
            to=phone,
            from_=twilio_number,
            body=f"Hello {customer['name']}, pay your EMI here: {link}"
        )
        logging.info(f"✅ SMS sent from {twilio_number} to {phone}, SID={msg.sid}, link={link}")
        return link

    except Exception:
        logging.exception("❌ Failed to send payment link SMS")
        return None


# ------------------ FLASK APP ------------------
app = Flask(__name__)

@app.before_request
def log_request():
    logging.info(f"{request.method} {request.path} from {request.remote_addr}")

# ------- /voice (Simplified for Render test) -------
@app.route("/voice", methods=["POST", "GET"])
def voice():
    logging.info("✅ /voice route triggered")
    resp = VoiceResponse()

    gather = Gather(num_digits=1, action="/handle-key", method="POST")
    gather.say(
        "Welcome to TVS Mitra. "
        "Press 1 to receive your EMI payment link via SMS. "
        "Press 2 to mark your EMI as paid. "
        "Press 3 to speak with an agent."
    )
    resp.append(gather)
    resp.redirect("/voice")

    xml_output = str(resp)
    logging.info(f"🔊 TwiML returned: {xml_output}")
    return Response(xml_output, mimetype="text/xml")

# ------- /handle-key -------
@app.route("/handle-key", methods=["POST"])
def handle_key():
    try:
        digit = request.form.get("Digits")
        from_number = request.values.get("From")
        to_number = request.values.get("To")
        logging.info(f"✅ /handle-key triggered | Digit={digit}, From={from_number}, To={to_number}")

        resp = VoiceResponse()
        customer = get_customer(to_number)

        if not customer:
            resp.say("We could not find your record. Please contact support.", voice="alice")
            resp.hangup()
            return Response(str(resp), mimetype="text/xml")

        if digit == "1":
            link = send_payment_link(customer)
            log_call_entry(customer["phone"], "dtmf_pay_link", "link_sent" if link else "link_failed", payment_link=link)
            resp.say("Payment link has been sent via SMS. Thank you.", voice="alice")

        elif digit == "2":
            mark_emi_paid(customer["phone"])
            log_call_entry(customer["phone"], "dtmf_mark_paid", "marked_paid")
            resp.say("Thank you. Your EMI has been marked as paid.", voice="alice")

        elif digit == "3":
            log_call_entry(customer["phone"], "dtmf_agent_request", "transfer")
            resp.say("Please wait while I connect you to an agent.", voice="alice")
            resp.dial("+911234567890")

        else:
            resp.say("Invalid input. Goodbye.", voice="alice")

        resp.hangup()
        return Response(str(resp), mimetype="text/xml")

    except Exception:
        logging.exception("Error in /handle-key")
        return Response("<Response><Say>Sorry, something went wrong.</Say></Response>", mimetype="text/xml")

# ------- /sms -------
@app.route("/sms", methods=["POST"])
def sms_reply():
    try:
        body = request.form.get("Body", "").strip()
        from_number = request.form.get("From")
        logging.info(f"Incoming SMS from {from_number}: {body}")

        resp = MessagingResponse()
        customer = get_customer(from_number)

        if body.lower() in ["hi", "hello"]:
            resp.message("Hello! This is TVS Mitra. Reply with 'PAY' to get your EMI payment link.")
        elif body.lower() == "pay" and customer:
            link = create_razorpay_payment_link(customer["name"], customer["phone"], customer["emi_amount"])
            resp.message(f"Hello {customer['name']}! Pay your EMI here: {link}")
            log_call_entry(customer["phone"], "sms_pay_request", "link_sent" if link else "link_failed", payment_link=link)
        else:
            resp.message("Sorry, I didn’t understand. Reply with 'PAY' to get your EMI link.")

        return str(resp)
    except Exception:
        logging.exception("Error in /sms endpoint")
        return str(MessagingResponse().message("Something went wrong. Please try again later."))

# ------- Run -------
@app.route("/", methods=["GET"])
def home():
    return "✅ TVS Mitra v2 is running correctly", 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    logging.info(f"🚀 Starting TVS Mitra v2 on port {port}")
    app.run(host="0.0.0.0", port=port)
