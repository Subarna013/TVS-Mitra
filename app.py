import os
import logging
from flask import Flask, request, Response
from twilio.twiml.voice_response import VoiceResponse, Gather
from twilio.twiml.messaging_response import MessagingResponse
from twilio.rest import Client
from sqlalchemy import create_engine, Table, MetaData, select
import razorpay
from dotenv import load_dotenv

# ------------------ SETUP ------------------
load_dotenv()
logging.basicConfig(level=logging.INFO)

# Twilio setup
twilio_sid = os.getenv("REMOVED")
twilio_token = os.getenv("REMOVED")
twilio_number = os.getenv("TWILIO_PHONE_NUMBER")
twilio_client = Client(twilio_sid, twilio_token)

# Razorpay setup
RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET")
rzp_client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))

# Database setup
DATABASE_URL = os.getenv("DATABASE_URL")  # Set this in Render
engine = create_engine(DATABASE_URL)
metadata = MetaData()
customers = Table('customers', metadata, autoload_with=engine)

# ------------------ HELPERS ------------------
def get_customer(phone_number):
    try:
        with engine.connect() as conn:
            query = select(customers).where(customers.c.phone == phone_number)
            row = conn.execute(query).fetchone()
            logging.info(f"Fetched customer for {phone_number}: {row}")
            return row
    except Exception:
        logging.exception("Error fetching customer from DB")
        return None

def create_razorpay_payment_link(customer_name, customer_contact, amount_rupees, description=None):
    try:
        amount_paise = int(round(float(amount_rupees) * 100))
        payload = {
            "amount": amount_paise,
            "currency": "INR",
            "accept_partial": False,
            "description": description or f"EMI payment for {customer_name}",
            "customer": {
                "name": customer_name,
                "contact": customer_contact,
                "email": "test@example.com"
            },
            "notify": {"sms": True, "email": False},
            "reminder_enable": True
        }
        resp = rzp_client.payment_link.create(payload)
        short_url = resp.get("short_url") or resp.get("shortLink")
        logging.info(f"Razorpay link created for {customer_contact}: {short_url}")
        return short_url
    except Exception:
        logging.exception("Failed to create Razorpay payment link")
        return None

# ------------------ FLASK APP ------------------
app = Flask(__name__)

# --------- Voice Entry Point ---------
@app.route("/voice", methods=["POST", "GET"])
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
    try:
        resp = VoiceResponse()
        digit = request.form.get("Digits")
        caller_number = request.values.get('From')
        logging.info(f"Received key press: {digit} from caller: {caller_number}")

        customer = get_customer(caller_number)
        logging.info(f"Customer fetched: {customer}")

        if digit == "1":
            resp.say("Great! Sending you a secure payment link via SMS now.")
            try:
                my_number = os.getenv("MY_NUMBER")
                payment_link = create_razorpay_payment_link(
                    customer_name=customer['name'] if customer else "Customer",
                    customer_contact=my_number,
                    amount_rupees=1000  # example EMI amount
                )
                message_body = f"Hello {customer['name'] if customer else 'Customer'}! Pay your EMI here: {payment_link or 'https://example.com/pay'}"
                message = twilio_client.messages.create(
                    to=my_number,
                    from_=twilio_number,
                    body=message_body
                )
                logging.info(f"SMS sent successfully! SID: {message.sid}, Status: {message.status}")
            except Exception:
                logging.exception("Failed to send SMS via Twilio")
                resp.say("We couldn't send the SMS right now. Please try later.")

        elif digit == "2":
            resp.say("Thank you. We have marked your EMI as paid.")
            logging.info("Marked EMI as paid.")

        elif digit == "3":
            resp.say("Please wait while we connect you to an agent.")
            logging.info("Connecting to agent...")
            resp.dial("+911234567890")  # replace with real agent number(s)

        else:
            resp.say("Sorry, invalid choice. Goodbye.")
            logging.info(f"Invalid key pressed: {digit}")

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
        if body.lower() in ["hi", "hello"]:
            resp.message("Hello! This is TVS Mitra. Reply with 'PAY' to get your EMI payment link.")
        elif body.lower() == "pay":
            resp.message("Here is your secure payment link: https://example.com/pay")
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
