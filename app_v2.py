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

# Tables (reflect)
customers = Table("customers", metadata, autoload_with=engine)
# call_logs should exist; if not, create_call_logs.py can be run earlier
call_logs = Table("call_logs", metadata, autoload_with=engine)  # will raise if missing

# ------------------ UTILITIES ------------------
def normalize_phone(phone: str):
    if not phone:
        return None
    phone = phone.strip()
    if phone.startswith("0"):
        phone = phone.lstrip("0")
    if not phone.startswith("+"):
        # assume India numbers for this MVP
        phone = "+91" + phone.lstrip("+")
    return phone

def simple_intent_and_sentiment(text: str):
    """Return (intent, sentiment, detected_text). Simple keywords-based classifier for MVP."""
    if not text:
        return "unknown", "neutral", ""
    txt = text.lower()
    # sentiment simple
    negative_words = ["problem", "can't", "cannot", "later", "busy", "sick", "loss", "unable", "sorry"]
    positive_words = ["paid", "done", "ok", "okay", "yes", "paid today", "completed"]
    sentiment = "neutral"
    if any(w in txt for w in negative_words):
        sentiment = "negative"
    if any(w in txt for w in positive_words):
        sentiment = "positive"

    # intents
    if any(phrase in txt for phrase in ["pay now", "send link", "i'll pay now", "i will pay now", "ready to pay", "pay today"]):
        intent = "pay_now"
    elif any(phrase in txt for phrase in ["tomorrow", "later", "next", "i'll pay", "i will pay", "pay later"]):
        intent = "promise_to_pay"
    elif any(phrase in txt for phrase in ["already paid", "i paid", "paid"]):
        intent = "paid"
    elif any(phrase in txt for phrase in ["busy", "call later", "call me later", "not now"]):
        intent = "reschedule"
    elif any(phrase in txt for phrase in ["who are you", "not interested", "stop", "unsubscribe"]):
        intent = "refused"
    else:
        intent = "unknown"

    return intent, sentiment, text.strip()

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

# ------------------ HELPERS ------------------
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
            stmt = update(customers).where(customers.c.phone == phone).values(payment_status="Paid", last_call_status="Paid")
            res = conn.execute(stmt)
            return res.rowcount > 0
    except Exception:
        logging.exception("Failed to mark paid")
        return False

def mark_promise(phone_number: str, promise_text=None):
    phone = normalize_phone(phone_number)
    if not phone:
        return False
    try:
        with engine.begin() as conn:
            stmt = update(customers).where(customers.c.phone == phone).values(last_call_status="Promise", last_call_date=date.today())
            conn.execute(stmt)
            return True
    except Exception:
        logging.exception("Failed to set promise")
        return False

def send_payment_link(customer):
    """Create razorpay link and send via Twilio SMS. Returns link or None."""
    try:
        link = create_razorpay_payment_link(customer["name"], customer["phone"], customer["emi_amount"])
        if link:
            twilio_client.messages.create(to=customer["phone"], from_=twilio_number, body=f"Hello {customer['name']}, pay your EMI: {link}")
        return link
    except Exception:
        logging.exception("Failed to send payment link")
        return None

def create_razorpay_payment_link(customer_name, customer_contact, amount_rupees):
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
        logging.info(f"Razorpay link created: {link}")
        return link
    except Exception:
        logging.exception("Razorpay error")
        return None

# ------------------ FLASK APP ------------------
app = Flask(__name__)

# Simple before-request logger
@app.before_request
def log_request():
    logging.info(f"{request.method} {request.path} from {request.remote_addr}")

# ------- /voice : entry point (speech gather with DTMF fallback) -------
@app.route("/voice", methods=["POST"])
def voice():
    resp = VoiceResponse()
    # bilingual greeting (English then Hindi short)
    resp.say("Hello. This is TVS Mitra calling regarding your EMI.", voice="alice")  # Twilio default voice
    resp.say("Namaste, ye TVS Mitra se phone hai aapke EMI ke sambandh mein.", voice="alice")
    # speech gather
    gather = Gather(input="speech", action="/handle-speech", method="POST", timeout=5, language="en-IN")
    gather.say("You can say, send link, I will pay tomorrow, or say 'busy' to request a callback.", voice="alice")
    resp.append(gather)
    # fallback to digit gather
    fallback = Gather(num_digits=1, action="/handle-key", method="POST")
    fallback.say("Or press 1 to receive a payment link, 2 to mark paid, 3 to speak with an agent.", voice="alice")
    resp.append(fallback)
    resp.redirect("/voice")
    return Response(str(resp), mimetype="text/xml")

# ------- /handle-speech : process speech input -------
@app.route("/handle-speech", methods=["POST"])
def handle_speech():
    try:
        speech_text = request.form.get("SpeechResult", "") or ""
        from_number = request.values.get("From")
        to_number = request.values.get("To")
        logging.info(f"SpeechResult='{speech_text}' FROM={from_number} TO={to_number}")

        customer = get_customer(to_number)
        if not customer:
            vr = VoiceResponse()
            vr.say("We could not find your record. Please contact support.", voice="alice")
            vr.hangup()
            return Response(str(vr), mimetype="text/xml")

        intent, sentiment, raw = simple_intent_and_sentiment(speech_text)

        # Decide actions
        if intent == "pay_now":
            link = send_payment_link(customer)
            log_call_entry(customer["phone"], "speech_pay_now", f"link_sent" if link else "link_failed", payment_link=link, customer_id=customer["id"])
            vr = VoiceResponse()
            if link:
                vr.say("We have sent a secure payment link to your phone via SMS. Thank you.", voice="alice")
            else:
                vr.say("We could not generate the payment link now. Please try again later.", voice="alice")
            vr.hangup()
            return Response(str(vr), mimetype="text/xml")

        elif intent == "promise_to_pay":
            mark_promise(customer["phone"], raw)
            log_call_entry(customer["phone"], "speech_promise", f"promise_recorded:{raw}", customer_id=customer["id"])
            vr = VoiceResponse()
            vr.say("Okay, noted. We will remind you on the promised date. Thank you.", voice="alice")
            vr.hangup()
            return Response(str(vr), mimetype="text/xml")

        elif intent == "paid":
            ok = mark_emi_paid(customer["phone"])
            log_call_entry(customer["phone"], "speech_paid", "marked_paid" if ok else "mark_failed", customer_id=customer["id"])
            vr = VoiceResponse()
            vr.say("Thank you. We have updated your account as paid. Have a nice day.", voice="alice")
            vr.hangup()
            return Response(str(vr), mimetype="text/xml")

        elif intent == "reschedule":
            log_call_entry(customer["phone"], "speech_reschedule", "asked_callback", customer_id=customer["id"])
            vr = VoiceResponse()
            vr.say("No problem. We will call you later. Thank you.", voice="alice")
            vr.hangup()
            return Response(str(vr), mimetype="text/xml")

        elif intent == "refused":
            log_call_entry(customer["phone"], "speech_refused", raw, customer_id=customer["id"])
            vr = VoiceResponse()
            vr.say("Okay. We will not bother you further. Goodbye.", voice="alice")
            vr.hangup()
            return Response(str(vr), mimetype="text/xml")

        else:
            # Unknown intent: offer to send link or speak to agent
            vr = VoiceResponse()
            vr.say("Sorry, I did not quite understand. Press 1 to receive a payment link or 3 to speak to an agent.", voice="alice")
            vr.redirect("/voice")
            log_call_entry(customer["phone"], "speech_unknown", raw, customer_id=customer["id"])
            return Response(str(vr), mimetype="text/xml")

    except Exception:
        logging.exception("Error in /handle-speech")
        return Response("<Response><Say>Sorry, something went wrong.</Say></Response>", mimetype="text/xml")

# ------- /handle-key : keep DTMF flow compatible with v1 -------
@app.route("/handle-key", methods=["POST"])
def handle_key():
    try:
        digit = request.form.get("Digits")
        from_number = request.values.get("From")
        to_number = request.values.get("To")
        logging.info(f"DTMF Digit={digit} FROM={from_number} TO={to_number}")

        customer = get_customer(to_number)
        vr = VoiceResponse()

        if not customer:
            vr.say("We could not find your record. Please contact support.", voice="alice")
            vr.hangup()
            return Response(str(vr), mimetype="text/xml")

        if digit == "1":
            link = send_payment_link(customer)
            log_call_entry(customer["phone"], "dtmf_pay_link", "link_sent" if link else "link_failed", payment_link=link, customer_id=customer["id"])
            if link:
                vr.say("Payment link has been sent via SMS. Thank you.", voice="alice")
            else:
                vr.say("Could not create payment link now. Please try again later.", voice="alice")
            vr.hangup()
            return Response(str(vr), mimetype="text/xml")

        elif digit == "2":
            ok = mark_emi_paid(customer["phone"])
            log_call_entry(customer["phone"], "dtmf_mark_paid", "marked_paid" if ok else "mark_failed", customer_id=customer["id"])
            if ok:
                vr.say("Thank you. Your EMI has been marked as paid.", voice="alice")
            else:
                vr.say("Unable to mark payment. Please contact support.", voice="alice")
            vr.hangup()
            return Response(str(vr), mimetype="text/xml")

        elif digit == "3":
            log_call_entry(customer["phone"], "dtmf_agent_request", "transfer")
            vr.say("Please wait while I connect you to an agent.", voice="alice")
            vr.dial("+911234567890")  # replace with real agent
            return Response(str(vr), mimetype="text/xml")

        else:
            vr.say("Invalid input. Goodbye.", voice="alice")
            vr.hangup()
            return Response(str(vr), mimetype="text/xml")

    except Exception:
        logging.exception("Error in /handle-key")
        return Response("<Response><Say>Sorry, something went wrong.</Say></Response>", mimetype="text/xml")

# ------- /sms endpoint (unchanged behaviour) -------
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
            log_call_entry(customer["phone"], "sms_pay_request", "link_sent" if link else "link_failed", payment_link=link, customer_id=customer["id"])
        else:
            resp.message("Sorry, I didn’t understand. Reply with 'PAY' to get your EMI link.")

        return str(resp)
    except Exception:
        logging.exception("Error in /sms endpoint")
        return str(MessagingResponse().message("Something went wrong. Please try again later."))

# ------- Run -------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    logging.info(f"Starting TVS Mitra v2 on port {port}")
    app.run(host="0.0.0.0", port=port)
