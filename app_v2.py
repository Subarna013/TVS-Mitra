import os
import logging
from datetime import datetime
from flask import Flask, request, Response, jsonify
from twilio.twiml.voice_response import VoiceResponse, Gather
from twilio.twiml.messaging_response import MessagingResponse
from twilio.rest import Client
from sqlalchemy import create_engine, Table, MetaData, select, update, insert
import razorpay
from dotenv import load_dotenv
import hmac
import hashlib

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
    phone = phone.strip().replace(" ", "").replace("-", "")
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
                    created_at=datetime.utcnow(),
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
            stmt = (
                update(customers)
                .where(customers.c.phone == phone)
                .values(payment_status="Paid")
            )
            conn.execute(stmt)
            logging.info(f"✅ EMI marked as paid for {phone}")
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
            "customer": {
                "name": customer_name,
                "contact": customer_contact,
                "email": "no-reply@example.com",
            },
            "notify": {"sms": True, "email": False},
            "reminder_enable": True,
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
        phone = normalize_phone(customer["phone"])

        # 1) Try to create Razorpay link
        link = create_razorpay_payment_link(
            customer_name=customer["name"],
            customer_contact=phone,
            amount_rupees=customer["emi_amount"],
        )

        # 2) Fallback link if Razorpay fails
        if not link:
            link = "https://example.com/demo-emi-payment"
            logging.warning("⚠️ Razorpay link failed, using fallback demo link.")

        # 3) Send SMS
        msg = twilio_client.messages.create(
            to=phone,
            from_=twilio_number,
            body=f"Hello {customer['name']}, pay your EMI here: {link}",
        )
        logging.info(
            f"✅ SMS sent from {twilio_number} to {phone}, SID={msg.sid}, link={link}"
        )
        return link

    except Exception:
        logging.exception("❌ Failed to send payment link SMS")
        return None


# ------------------ FLASK APP ------------------
app = Flask(__name__)


@app.before_request
def log_request():
    logging.info(f"{request.method} {request.path} from {request.remote_addr}")


# ------- /voice -------
@app.route("/voice", methods=["POST", "GET"])
def voice():
    logging.info("✅ /voice route triggered")
    resp = VoiceResponse()

    # ---------------- BUCKET DETECTION ----------------
    bucket = request.args.get("bucket", "due")  # "pre_due" or "due"
    logging.info(f"📌 Call bucket = {bucket}")

    # ---------------- CUSTOMER CONTEXT ----------------
    # For outbound calls: From = Twilio, To = customer
    to_number = request.values.get("To")
    logging.info(f"📞 /voice To={to_number}")
    customer = get_customer(to_number) if to_number else None

    # If we already know this EMI is paid, short-circuit
    if customer and customer.get("payment_status") == "Paid":
        resp.say(
            "Hello from TVS Mitra. Our records show your EMI is already paid. "
            "Thank you and have a great day.",
            voice="alice",
        )
        resp.hangup()
        return Response(str(resp), mimetype="text/xml")

    # Check recent history: has a pay-link been sent earlier?
    is_follow_up = False
    try:
        if customer:
            with engine.connect() as conn:
                recent = (
                    conn.execute(
                        select(call_logs)
                        .where(
                            call_logs.c.phone == customer["phone"],
                            call_logs.c.action.in_(
                                ["dtmf_pay_link", "sms_pay_request"]
                            ),
                        )
                        .order_by(call_logs.c.created_at.desc())
                    )
                    .mappings()
                    .fetchone()
                )
            if recent and customer.get("payment_status") == "Pending":
                is_follow_up = True
                logging.info(
                    f"📌 Follow-up call detected for {customer['phone']} (previous link sent)."
                )
    except Exception:
        logging.exception("Failed to check recent call_logs for follow-up detection")

    # ---------------- IVR SCRIPT ----------------
    if bucket == "pre_due":
        base_intro = "Your EMI is coming up soon."
    else:
        base_intro = "Your EMI payment is due."

    if is_follow_up:
        intro = (
            f"{base_intro} We recently sent you a payment link which is still pending. "
            "Press 1 to resend the payment link by SMS. "
            "Press 2 if you will pay later and want us to record your promise to pay. "
            "Press 3 to speak with an agent."
        )
    else:
        intro = (
            f"{base_intro} "
            "Press 1 to receive a secure payment link by SMS. "
            "Press 2 if you will pay later and want us to record your promise to pay. "
            "Press 3 to speak with an agent."
        )

    # Pass bucket to /handle-key for context
    gather = Gather(
        num_digits=1,
        action=f"/handle-key?bucket={bucket}",
        method="POST",
    )
    gather.say(f"Hello from TVS Mitra. {intro}", voice="alice")

    resp.append(gather)
    resp.redirect(f"/voice?bucket={bucket}")

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
        bucket = request.args.get("bucket", "due")
        logging.info(
            f"✅ /handle-key triggered | Digit={digit}, From={from_number}, "
            f"To={to_number}, bucket={bucket}"
        )

        resp = VoiceResponse()
        customer = get_customer(to_number)

        if not customer:
            resp.say(
                "We could not find your record. Please contact support.",
                voice="alice",
            )
            resp.hangup()
            return Response(str(resp), mimetype="text/xml")

        # Extra safety: if paid between /voice and /handle-key
        if customer.get("payment_status") == "Paid":
            resp.say(
                "Our records now show your EMI is already paid. Thank you.",
                voice="alice",
            )
            resp.hangup()
            return Response(str(resp), mimetype="text/xml")

        if digit == "1":
            link = send_payment_link(customer)
            log_call_entry(
                customer["phone"],
                "dtmf_pay_link",
                "link_sent" if link else "link_failed",
                payment_link=link,
                customer_id=customer["id"],
            )
            resp.say(
                "Payment link has been sent via SMS. Thank you.",
                voice="alice",
            )

        elif digit == "2":
            # 👉 PROMISE-TO-PAY (do NOT mark as paid)
            try:
                with engine.begin() as conn:
                    stmt = (
                        update(customers)
                        .where(customers.c.id == customer["id"])
                        .values(last_call_status="promise_to_pay")
                    )
                    conn.execute(stmt)

                log_call_entry(
                    customer["phone"],
                    "dtmf_promise_to_pay",
                    "promise_to_pay",
                    customer_id=customer["id"],
                )

                resp.say(
                    "Thank you. We have recorded your promise to pay soon. "
                    "You will receive a reminder before your due date.",
                    voice="alice",
                )
            except Exception:
                logging.exception("Failed to record promise_to_pay")
                resp.say(
                    "Sorry, we could not record your response. "
                    "Please try again later.",
                    voice="alice",
                )

        elif digit == "3":
            log_call_entry(
                customer["phone"],
                "dtmf_agent_request",
                "transfer",
                customer_id=customer["id"],
            )
            resp.say(
                "Please wait while I connect you to an agent.",
                voice="alice",
            )
            resp.dial("+911234567890")

        else:
            resp.say("Invalid input. Goodbye.", voice="alice")

        resp.hangup()
        return Response(str(resp), mimetype="text/xml")

    except Exception:
        logging.exception("Error in /handle-key")
        return Response(
            "<Response><Say>Sorry, something went wrong.</Say></Response>",
            mimetype="text/xml",
        )


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
            resp.message(
                "Hello! This is TVS Mitra. Reply with 'PAY' to get your EMI payment link."
            )
        elif body.lower() == "pay" and customer:
            link = create_razorpay_payment_link(
                customer["name"], customer["phone"], customer["emi_amount"]
            )
            if not link:
                link = "https://example.com/demo-emi-payment"
                logging.warning("⚠️ Razorpay link failed in /sms, using fallback.")
            resp.message(f"Hello {customer['name']}! Pay your EMI here: {link}")
            log_call_entry(
                customer["phone"],
                "sms_pay_request",
                "link_sent" if link else "link_failed",
                payment_link=link,
                customer_id=customer["id"],
            )
        else:
            resp.message(
                "Sorry, I didn’t understand. Reply with 'PAY' to get your EMI link."
            )

        return str(resp)
    except Exception:
        logging.exception("Error in /sms endpoint")
        return str(
            MessagingResponse().message(
                "Something went wrong. Please try again later."
            )
        )


# ------- Healthcheck -------
@app.route("/", methods=["GET"])
def home():
    return "✅ TVS Mitra v2 is running correctly", 200


# ---- Razorpay webhook --------
RAZORPAY_WEBHOOK_SECRET = os.getenv("RAZORPAY_WEBHOOK_SECRET")  # set in .env


@app.route("/razorpay/webhook", methods=["POST"])
def razorpay_webhook():
    try:
        if not RAZORPAY_WEBHOOK_SECRET:
            logging.error("RAZORPAY_WEBHOOK_SECRET is not set")
            return jsonify({"status": "webhook secret not configured"}), 500

        payload = request.data
        signature = request.headers.get("X-Razorpay-Signature")

        # ✅ Verify signature
        expected = hmac.new(
            RAZORPAY_WEBHOOK_SECRET.encode(), payload, hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(expected, signature or ""):
            logging.warning("⚠️ Invalid Razorpay webhook signature")
            return jsonify({"status": "invalid signature"}), 400

        data = request.get_json()
        event = data.get("event")

        if event == "payment_link.paid":
            payment_link_id = data["payload"]["payment_link"]["entity"]["id"]
            customer_phone = data["payload"]["payment_link"]["entity"]["customer"][
                "contact"
            ]

            customer = get_customer(customer_phone)
            if customer:
                mark_emi_paid(customer["phone"])
                log_call_entry(
                    customer["phone"],
                    "payment_link_paid",
                    "paid",
                    payment_link=payment_link_id,
                    customer_id=customer["id"],
                )

        return jsonify({"status": "ok"}), 200
    except Exception:
        logging.exception("Error handling Razorpay webhook")
        return jsonify({"status": "error"}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    logging.info(f"🚀 Starting TVS Mitra v2 on port {port}")
    app.run(host="0.0.0.0", port=port)
