import os
import logging
from flask import Flask, request, Response
from twilio.twiml.voice_response import VoiceResponse, Gather
from twilio.twiml.messaging_response import MessagingResponse
from twilio.rest import Client
from sqlalchemy import create_engine, Table, MetaData, select, update
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
customers = Table('customers', metadata, autoload_with=engine)

# ------------------ HELPERS ------------------
def get_customer(phone_number):
    """Fetch customer from DB by phone number, normalized"""
    try:
        # Ensure phone number is in standard format
        if not phone_number.startswith("+"):
            phone_number = "+91" + phone_number.lstrip("0")
        with engine.connect() as conn:
            query = select(customers).where(customers.c.phone == phone_number)
            row = conn.execute(query).fetchone()
            logging.info(f"Fetched customer: {row}")
            return row
    except Exception:
        logging.exception("Error fetching customer from DB")
        return None


def mark_emi_paid(phone_number):
    try:
        # Normalize number
        if not phone_number.startswith("+"):
            phone_number = "+91" + phone_number.lstrip("0")

        with engine.begin() as conn:  # auto commit
            stmt = update(customers).where(customers.c.phone == phone_number).values(payment_status="Paid")
            result = conn.execute(stmt)
            if result.rowcount == 0:
                logging.warning(f"No customer found with phone {phone_number}")
            else:
                logging.info(f"EMI marked as paid for {phone_number}")
    except Exception:
        logging.exception("Failed to update EMI status")


def create_razorpay_payment_link(customer_name, customer_contact, amount_rupees):
    """Create Razorpay payment link"""
    try:
        amount_paise = int(round(float(amount_rupees) * 100))
        payload = {
            "amount": amount_paise,
            "currency": "INR",
            "accept_partial": False,
            "description": f"EMI payment for {customer_name}",
            "customer": {
                "name": customer_name,
                "contact": customer_contact,
                "email": "test@example.com"
            },
            "notify": {"sms": True, "email": False},
            "reminder_enable": True
        }
        resp = rzp_client.payment_link.create(payload)
        link = resp.get("short_url") or resp.get("shortLink")
        logging.info(f"Razorpay link created: {link}")
        return link
    except Exception:
        logging.exception("Failed to create Razorpay link")
        return None

# ------------------ FLASK APP ------------------
app = Flask(__name__)

# --------- Voice Entry Point ---------
@app.route("/voice", methods=["POST"])
def voice():
    resp = VoiceResponse()
    gather = Gather(num_digits=1, action='/handle-key', method='POST')
    gather.say(
        "Welcome to TVS Mitra. "
        "Press 1 to receive your EMI payment link via SMS. "
        "Press 2 to mark your EMI as paid. "
        "Press 3 to speak with an agent."
    )
    resp.append(gather)
    resp.redirect('/voice')  # repeat if no input
    return Response(str(resp), mimetype="text/xml")

# --------- Handle Key Press ---------
@app.route("/handle-key", methods=["POST"])
def handle_key():
    resp = VoiceResponse()
    try:
        digit = request.form.get("Digits")
        caller_number = request.values.get('From')
        logging.info(f"Received key: {digit} from {caller_number}")

        customer = get_customer(caller_number)

        if digit == "1":
            if customer:
                payment_link = create_razorpay_payment_link(
                    customer_name=customer['name'],
                    customer_contact=customer['phone'],
                    amount_rupees=customer['emi_amount']
                )
                message_body = f"Hello {customer['name']}! Pay your EMI here: {payment_link or 'https://example.com/pay'}"
                twilio_client.messages.create(
                    to=customer['phone'],
                    from_=twilio_number,
                    body=message_body
                )
                resp.say("Payment link sent via SMS. Thank you!")
            else:
                resp.say("We could not find your record. Please contact support.")

        elif digit == "2":
            if customer:
                mark_emi_paid(caller_number)
                resp.say("Thank you. Your EMI has been marked as paid.")
            else:
                resp.say("We could not find your record. Please contact support.")

        elif digit == "3":
            resp.say("Please wait while we connect you to an agent.")
            resp.dial("+911234567890")  # Replace with real agent number

        else:
            resp.say("Invalid input. Goodbye.")
        resp.hangup()
        return Response(str(resp), mimetype="text/xml")

    except Exception:
        logging.exception("Error in /handle-key")
        return Response("<Response><Say>Sorry, something went wrong.</Say></Response>", mimetype="text/xml")

# --------- SMS Endpoint ---------
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
            payment_link = create_razorpay_payment_link(
                customer_name=customer['name'],
                customer_contact=customer['phone'],
                amount_rupees=customer['emi_amount']
            )
            resp.message(f"Hello {customer['name']}! Pay your EMI here: {payment_link}")
        else:
            resp.message("Sorry, I didn’t understand. Reply with 'PAY' to get your EMI link.")

        return str(resp)
    except Exception:
        logging.exception("Error in /sms endpoint")
        return str(MessagingResponse().message("Something went wrong. Please try again later."))

# --------- RUN APP ---------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    logging.info(f"Starting Flask app on port {port}")
    app.run(host="0.0.0.0", port=port)
