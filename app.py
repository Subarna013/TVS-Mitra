import os
import logging
from flask import Flask, request, Response
from twilio.twiml.voice_response import VoiceResponse, Gather
from twilio.twiml.messaging_response import MessagingResponse
from twilio.rest import Client
from sqlalchemy import create_engine, Table, MetaData, select, update, insert
import razorpay
from dotenv import load_dotenv

# ------------------ LOAD ENV ------------------
load_dotenv()
logging.basicConfig(level=logging.INFO)

# ------------------ TWILIO ------------------
twilio_sid = os.getenv("TWILIO_ACCOUNT_SID")
twilio_token = os.getenv("TWILIO_AUTH_TOKEN")
twilio_number = os.getenv("TWILIO_PHONE_NUMBER")
twilio_client = Client(twilio_sid, twilio_token)

# ------------------ RAZORPAY ------------------
rzp = razorpay.Client(auth=(
    os.getenv("RAZORPAY_KEY_ID"),
    os.getenv("RAZORPAY_KEY_SECRET")
))

# ------------------ DATABASE ------------------
engine = create_engine(os.getenv("DATABASE_URL"))
metadata = MetaData()
metadata.reflect(bind=engine)

customers = Table("customers", metadata, autoload_with=engine)

# OPTIONAL: call_logs if exists
call_logs = None
if "call_logs" in metadata.tables:
    call_logs = Table("call_logs", metadata, autoload_with=engine)


# ------------------ HELPERS ------------------
def normalize_phone(phone: str):
    if not phone:
        return None
    phone = phone.strip().replace(" ", "").replace("-", "")
    if phone.startswith("0"):
        phone = phone.lstrip("0")
    if not phone.startswith("+"):
        phone = "+91" + phone.lstrip("+")
    return phone


def log_call(phone, action, outcome, payment_link=None):
    if not call_logs:
        return
    try:
        with engine.begin() as conn:
            conn.execute(insert(call_logs).values(
                phone=phone,
                action=action,
                outcome=outcome,
                payment_link=payment_link
            ))
    except Exception:
        logging.exception("Failed to write to call_logs")


def get_customer(phone):
    phone = normalize_phone(phone)
    if not phone:
        return None
    try:
        with engine.connect() as conn:
            row = conn.execute(
                select(customers).where(customers.c.phone == phone)
            ).mappings().fetchone()
            logging.info(f"Fetched customer: {row}")
            return row
    except Exception:
        logging.exception("Error fetching customer")
        return None


def mark_paid(phone):
    phone = normalize_phone(phone)
    try:
        with engine.begin() as conn:
            conn.execute(
                update(customers)
                .where(customers.c.phone == phone)
                .values(payment_status="Paid")
            )
        logging.info(f"Marked Paid: {phone}")
    except Exception:
        logging.exception("Failed to update payment_status")


def create_payment_link(customer):
    """Generate Razorpay payment link with fallback."""
    try:
        amount = int(float(customer["emi_amount"]) * 100)
        payload = {
            "amount": amount,
            "currency": "INR",
            "accept_partial": False,
            "description": f"EMI for {customer['name']}",
            "customer": {
                "name": customer["name"],
                "contact": normalize_phone(customer["phone"]),
                "email": "no-reply@tvsmitra.com"
            },
            "notify": {"sms": True},
            "reminder_enable": True
        }

        resp = rzp.payment_link.create(payload)
        link = resp.get("short_url") or resp.get("shortLink")
        logging.info(f"Razorpay link: {link}")
        return link

    except Exception:
        logging.exception("Razorpay failed, using fallback")
        return "https://example.com/pay"


def send_payment_sms(customer):
    phone = normalize_phone(customer["phone"])
    link = create_payment_link(customer)

    try:
        msg = twilio_client.messages.create(
            to=phone,
            from_=twilio_number,
            body=f"Hello {customer['name']}, pay your EMI here: {link}"
        )
        logging.info(f"SMS sent to {phone}, SID={msg.sid}")
    except Exception:
        logging.exception("SMS sending failed")

    return link


# ------------------ FLASK ------------------
app = Flask(__name__)


@app.route("/voice", methods=["POST"])
def voice():
    resp = VoiceResponse()

    gather = Gather(num_digits=1, action="/handle-key", method="POST")
    gather.say(
        "Welcome to TVS Mitra. "
        "Press 1 for a payment link. "
        "Press 2 if you will pay later. "
        "Press 3 to speak with an agent.",
        voice="alice"
    )
    resp.append(gather)
    resp.redirect("/voice")
    return Response(str(resp), mimetype="text/xml")


@app.route("/handle-key", methods=["POST"])
def handle_key():
    digit = request.form.get("Digits")
    customer_number = request.values.get("To")  # actual customer number
    customer = get_customer(customer_number)

    resp = VoiceResponse()

    if not customer:
        resp.say("Your record could not be found.", voice="alice")
        resp.hangup()
        return Response(str(resp), mimetype="text/xml")

    # Already paid case
    if customer["payment_status"] == "Paid":
        resp.say("Your EMI is already paid. Thank you!", voice="alice")
        resp.hangup()
        return Response(str(resp), mimetype="text/xml")

    # ------------------ OPTION 1: Payment Link ------------------
    if digit == "1":
        link = send_payment_sms(customer)
        log_call(customer["phone"], "dtmf_pay_link", "sent", payment_link=link)
        resp.say("Your payment link has been sent by SMS.", voice="alice")

    # ------------------ OPTION 2: Promise to Pay ------------------
    elif digit == "2":
        log_call(customer["phone"], "dtmf_promise_to_pay", "promise")
        resp.say("Okay. We have noted that you will pay soon.", voice="alice")

    # ------------------ OPTION 3: Agent ------------------
    elif digit == "3":
        log_call(customer["phone"], "dtmf_agent", "transfer")
        resp.say("Connecting you to our support agent.", voice="alice")
        resp.dial("+911234567890")

    else:
        resp.say("Invalid input.", voice="alice")

    resp.hangup()
    return Response(str(resp), mimetype="text/xml")


@app.route("/sms", methods=["POST"])
def sms_reply():
    body = request.form.get("Body", "").strip().lower()
    from_number = request.form.get("From")

    resp = MessagingResponse()
    customer = get_customer(from_number)

    if not customer:
        resp.message("Record not found.")
        return str(resp)

    if body in ["hi", "hello"]:
        resp.message("Reply PAY for your EMI payment link.")
    elif body == "pay":
        link = create_payment_link(customer)
        log_call(customer["phone"], "sms_pay", "link_sent", payment_link=link)
        resp.message(f"Hello {customer['name']}, pay here: {link}")
    else:
        resp.message("I did not understand. Reply PAY.")

    return str(resp)


# Health Check
@app.route("/")
def home():
    return "TVS Mitra Basic IVR Running", 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
