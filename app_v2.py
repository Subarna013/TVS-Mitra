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
import difflib
from intents_inference import predict_intent
from sentiments_inference import predict_sentiment
import google.generativeai as genai
from payment_inference import predict_payment_probability
import numpy as np
import psycopg2

# ------------------ SETUP ------------------
load_dotenv()
logging.basicConfig(level=logging.INFO)

# ------------------ RAG FEATURE FLAG ------------------
# Turn this ON locally in .env (USE_POLICY_RAG=true)
# Turn this OFF on Render to avoid OOM
USE_POLICY_RAG = os.getenv("USE_POLICY_RAG", "false").lower() == "true"

policy_model = None
if USE_POLICY_RAG:
    try:
        from sentence_transformers import SentenceTransformer
        EMB_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
        policy_model = SentenceTransformer(EMB_MODEL_NAME)
        logging.info(f"✅ Policy embedding model loaded: {EMB_MODEL_NAME}")
    except Exception:
        logging.exception("❌ Failed to load policy embedding model")
        policy_model = None
else:
    logging.info("ℹ️ Policy RAG disabled (USE_POLICY_RAG != true)")

# ------------------ GEMINI SETUP ------------------
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
gemini_model = None

if GEMINI_API_KEY:
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        gemini_model = genai.GenerativeModel("gemini-1.5-flash")
        logging.info("✅ Gemini model initialised.")
    except Exception:
        logging.exception("❌ Failed to init Gemini model")
        gemini_model = None
else:
    logging.warning("⚠️ GEMINI_API_KEY not set. Gemini features disabled.")

# Twilio setup
twilio_sid = os.getenv("TWILIO_ACCOUNT_SID")
twilio_token = os.getenv("TWILIO_AUTH_TOKEN")
twilio_number = os.getenv("TWILIO_PHONE_NUMBER")
twilio_client = Client(twilio_sid, twilio_token)

# WhatsApp (Sandbox) sender
TWILIO_WHATSAPP_NUMBER = "whatsapp:+14155238886"  # Twilio WhatsApp Sandbox number

# Razorpay setup
RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET")
rzp_client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))

# Database setup
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("❌ DATABASE_URL missing in environment variables")

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

    # Handle Twilio WhatsApp format: "whatsapp:+9190..."
    if phone.startswith("whatsapp:"):
        phone = phone[len("whatsapp:"):]  # remove the prefix

    # Remove spaces and dashes
    phone = phone.replace(" ", "").replace("-", "")

    # Remove leading 0s (e.g. 09123456789 -> 9123456789)
    if phone.startswith("0"):
        phone = phone.lstrip("0")

    # Ensure +91, but avoid double 91
    if phone.startswith("+"):
        return phone

    # If already looks like 91XXXXXXXXXX, just add +
    if phone.startswith("91") and len(phone) == 12:
        phone = "+" + phone
    else:
        phone = "+91" + phone.lstrip("+")

    return phone


import difflib  # already imported, but kept here for clarity


def fuzzy_contains_any(text: str, keywords: list[str], cutoff: float = 0.8) -> bool:
    """
    Return True if *any* keyword is present in text either:
    - as a substring, or
    - as a 'close' word (e.g. 'fruud' ~ 'fraud').
    """
    text_low = (text or "").lower()
    # direct substring match
    for kw in keywords:
        if kw in text_low:
            return True

    # token-level fuzzy match
    words = text_low.split()
    for w in words:
        for kw in keywords:
            if difflib.SequenceMatcher(None, w, kw).ratio() >= cutoff:
                return True

    return False


def looks_like_already_paid(text: str) -> bool:
    """Detect variations like 'but i paid', 'i already paid', 'payment done' etc."""
    t = (text or "").lower()

    patterns = [
        "already paid",
        "i already paid",
        "payment done",
        "paid already",
        "but i paid",
        "but i have paid",
    ]
    if any(p in t for p in patterns):
        return True

    # 'i paid', 'paid' (simple exact short variants)
    if t.strip() in ["i paid", "paid"]:
        return True

    # fuzzy: "i alredi pad" etc
    if "already" in t and fuzzy_contains_any(t, ["paid", "payment"], cutoff=0.8):
        return True

    return False


def looks_like_why_pay(text: str) -> bool:
    """Detect 'why should I pay', 'why pay', etc."""
    t = (text or "").lower()

    if "why" in t and fuzzy_contains_any(t, ["pay"], cutoff=0.8):
        return True
    if "should i" in t and fuzzy_contains_any(t, ["pay"], cutoff=0.8):
        return True

    return False


def looks_like_hardship(text: str) -> bool:
    """
    Detect hardship cases: 'can't pay', 'cannot pay', 'lost my job', etc.
    Uses fuzzy_contains_any so small typos are okay.
    """
    t = (text or "").lower()

    cant_words = ["cant", "can't", "cannot", "can not", "unable"]
    if fuzzy_contains_any(t, cant_words, cutoff=0.7) and fuzzy_contains_any(
        t, ["pay"], cutoff=0.8
    ):
        return True

    # lost job / income issues
    if fuzzy_contains_any(t, ["lost"], cutoff=0.8) and fuzzy_contains_any(
        t, ["job", "income", "salary"], cutoff=0.7
    ):
        return True

    return False


def looks_like_question(text: str) -> bool:
    """
    Detect natural-language questions like:
    - what happens if...
    - why are you...
    - how can I...
    - when will...
    """
    t = (text or "").strip().lower()
    if not t:
        return False

    # ends with a question mark
    if t.endswith("?"):
        return True

    question_patterns = [
        "what ",
        "why ",
        "how ",
        "when ",
        "where ",
        "which ",
        "who ",
        "can i ",
        "should i ",
        "do i have to ",
        "what happens",
        "what will happen",
    ]

    for q in question_patterns:
        if t.startswith(q) or f" {q}" in t:
            return True

    return False


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
    """Send Razorpay payment link via WhatsApp (with fallback + phone normalization)."""
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

        # 3) Send WhatsApp message
        msg = twilio_client.messages.create(
            to=f"whatsapp:{phone}",
            from_=TWILIO_WHATSAPP_NUMBER,
            body=f"Hello {customer['name']}, pay your EMI here: {link}",
        )

        logging.info(
            f"✅ WhatsApp sent from {TWILIO_WHATSAPP_NUMBER} to {phone}, SID={msg.sid}, link={link}"
        )
        return link

    except Exception:
        logging.exception("❌ Failed to send payment link WhatsApp")
        return None


def llm_fallback_reply(user_text: str, customer: dict | None) -> str:
    """
    Fallback reply when no specific rule matched.
    No external LLM used here – we keep it simple + safe.
    """
    return (
        "I'm still learning to handle more questions.\n"
        "Right now I can help you with your EMI basics:\n"
        "- Type 'PAY' to get your EMI link\n"
        "- Type 'STATUS' to see EMI amount and status\n"
        "- Type 'WHY SHOULD I PAY' to understand your EMI\n"
        "- Type 'I ALREADY PAID' if you've already paid\n"
        "- 'AGENT' to talk to a human\n"
    )


def gemini_policy_answer(
    user_text: str, customer: dict | None, extra_context: list[str] | None = None
) -> str:
    """
    Policy-aware answer function.

    Priority:
    1) If Gemini works -> use it with RAG context.
    2) If Gemini fails but we have policy chunks -> build a safe, rule-based answer from chunks.
    3) If nothing works -> fall back to simple menu reply.
    """
    # ---------- 1) Build customer + doc context ----------
    customer_context = ""
    if customer:
        customer_context = (
            "Customer EMI context (may be partial):\n"
            f"- Name: {customer.get('name')}\n"
            f"- EMI amount: {customer.get('emi_amount')}\n"
            f"- Due date: {customer.get('due_date')}\n"
            f"- Payment status: {customer.get('payment_status')}\n"
            f"- Last call status: {customer.get('last_call_status')}\n"
        )

    doc_context = ""
    if extra_context:
        joined = "\n\n---\n".join(extra_context)
        doc_context = (
            "Here are relevant excerpts from TVS Credit policies and FAQs.\n"
            "Use ONLY this information plus general EMI concepts. "
            "If something is not clearly specified, say that exact details depend on the customer's loan agreement "
            "and they should contact TVS Credit support.\n\n"
            f"{joined}\n\n"
        )

    system_instruction = (
        "You are TVS Mitra, an EMI collections assistant for TVS Credit.\n"
        "You must answer based ONLY on:\n"
        "- The policy excerpts provided, and\n"
        "- General high-level EMI/credit knowledge.\n"
        "NEVER invent exact fees, dates, or promises.\n"
    )

    prompt = (
        system_instruction
        + "\n\n"
        + customer_context
        + "\n"
        + doc_context
        + "User question:\n"
        + user_text
    )

    # ---------- 2) Try Gemini if available ----------
    if gemini_model is not None:
        try:
            resp = gemini_model.generate_content(prompt)
            answer = (resp.text or "").strip()
            if answer:
                return answer
        except Exception:
            logging.exception("Gemini policy answer failed – falling back to template")

    # ---------- 3) If Gemini failed BUT we have policy chunks, use them directly ----------
    if extra_context:
        bullets = "\n\n".join(f"- {c}" for c in extra_context)
        return (
            "Here is information based on TVS Credit’s standard EMI and collection policies:\n"
            f"{bullets}\n\n"
            "Note: Exact charges, dates and actions can vary by product and your specific loan agreement. "
            "For precise details, please refer to your sanction letter / schedule of charges "
            "or contact TVS Credit customer support."
        )

    # ---------- 4) Last resort ----------
    return llm_fallback_reply(user_text, customer)


def handle_text_message(body: str, from_number: str) -> str:
    """
    Common handler for SMS + Web chat messages.
    Uses:
      - ML intent classifier
      - Sentiment classifier
      - Gemini for FAQ/policy/general questions
      - Payment prediction model
      - Existing rule-based logic for EMI flows
    """
    text = (body or "").strip().lower()
    customer = get_customer(from_number)

    # 🔮 Optional: predictive score (may be None if model not loaded)
    payment_prob = None
    if customer:
        try:
            payment_prob = predict_payment_probability(customer)
        except Exception:
            logging.exception("Payment prediction failed")
            payment_prob = None

    # -------- 🔮 0) Predict intent + sentiment using ML models --------
    intent, intent_conf = predict_intent(text)
    sentiment, sent_conf = predict_sentiment(text)

    logging.info(
        f"🧠 Intent={intent} ({intent_conf:.2f}), "
        f"Sentiment={sentiment} ({sent_conf:.2f})"
    )

    def is_intent(label: str, threshold: float = 0.6) -> bool:
        return intent == label and (intent_conf or 0.0) >= threshold

    def is_negative(threshold: float = 0.6) -> bool:
        return (sentiment in ["ANGRY", "NEGATIVE"]) and (sent_conf or 0.0) >= threshold

    def is_angry(threshold: float = 0.6) -> bool:
        return (sentiment == "ANGRY") and (sent_conf or 0.0) >= threshold

    # -------- 🔥 0.1 Dispute / harassment / DNC detection (high-priority) --------
    dispute_keywords = [
        "fraud",
        "cheat",
        "scam",
        "harass",
        "harassment",
        "harrasment",  # typo
        "harassing",
        "police",
        "legal",
        "case",
        "consumer court",
        "complaint",
        "wrong number",
        "do not call",
        "dont call",
        "don't call",
        "stop calling",
        "stop messaging",
        "stop msg",
        "disturbing me",
        "stop disturbing",
    ]

    # fuzzy match single-word typos like "fruud" ~ "fraud"
    base_roots = ["fraud", "scam", "cheat", "harass"]
    has_dispute_word = fuzzy_contains_any(text, dispute_keywords, cutoff=0.8) or (
        fuzzy_contains_any(text, base_roots, cutoff=0.8)
    )

    if has_dispute_word:
        return (
            "I'm really sorry you're facing this issue.\n"
            "This looks like a dispute, complaint or a request to stop communication. "
            "For your safety and proper resolution, a human agent should handle this.\n"
            "We will avoid further automated messages on this channel.\n"
            "Please contact TVS Credit customer care or type 'AGENT' and we will arrange a call back."
        )

    if is_negative() and any(k in text for k in dispute_keywords):
        return (
            "I'm really sorry you're facing this issue.\n"
            "This looks like a dispute or complaint. "
            "For your safety and proper resolution, a human agent should handle this.\n"
            "Please contact TVS Credit customer care or type 'AGENT' and we will arrange a call back."
        )

    # -------- 1) GREET / HELP (intent or keyword) --------
    if is_intent("GREET") or text in ["hi", "hello", "hey"]:
        return (
            "Hello! This is TVS Mitra.\n"
            "You can type:\n"
            "- 'PAY' to get your EMI payment link\n"
            "- 'STATUS' to check your EMI status\n"
            "- 'WHY SHOULD I PAY' to understand your EMI\n"
            "- 'I ALREADY PAID' if you have already paid\n"
            "- 'AGENT' to request a call from an agent\n"
        )

    if is_intent("HELP_MENU") or "help" in text or "options" in text or "menu" in text:
        return (
            "Here are some things I can help with:\n"
            "- 'PAY' → get EMI payment link\n"
            "- 'STATUS' → see EMI amount, due date, status\n"
            "- 'WHY SHOULD I PAY' → reason for this EMI\n"
            "- 'I ALREADY PAID' → tell us you paid\n"
            "- 'AGENT' → ask for a human to call you\n"
        )

    # -------- HARDSHIP / CANNOT PAY --------
    if looks_like_hardship(text):
        return (
            "I'm sorry to hear you're facing financial difficulty.\n\n"
            "Here are a few options you can consider:\n"
            "- Talk to a TVS Credit agent about possible options like rescheduling or restructuring.\n"
            "- Try not to ignore the EMI completely, as it can affect your credit score and future loans.\n"
            "- If you expect income soon, you can ask if a short extension is possible.\n\n"
            "For detailed help, it's best to speak to a human agent. "
            "You can type 'AGENT' and we will arrange a call back."
        )

    # -------- 💬 Small-talk / fun replies --------
    if "love you" in text or "luv u" in text or "i love u" in text:
        return "Haha, I'm just your TVS Mitra EMI assistant, but I'm always here to help you 🤝"

    if is_intent("SMALL_TALK") or "joke" in text or "funny" in text or "laugh" in text:
        return "Here’s a finance joke: Why did the EMI go to school? To become a little more payable every month. 😄"

    # Extra small-talk patterns not covered by intent model
    if "who are u" in text or "who r u" in text or "who are you" in text:
        return (
            "I'm TVS Mitra, an EMI assistant from TVS Credit.\n"
            "I can help you with:\n"
            "- Your EMI payment link (type 'PAY')\n"
            "- EMI amount and status (type 'STATUS')\n"
            "- Questions about why and how to pay\n"
            "- Connecting you to an agent (type 'AGENT')"
        )

    if fuzzy_contains_any(text, ["marry", "marriage"], cutoff=0.8):
        return (
            "Haha 😄 I'm just a virtual EMI assistant, not a human.\n"
            "But I promise to be loyal in reminding you about your EMIs!"
        )

    # -------- 2) Customer not found --------
    if not customer:
        if "why" in text and "pay" in text:
            return (
                "This channel is for TVS Credit customers with active EMIs. "
                "We couldn't find your record linked to this number. "
                "If you think this is wrong, please contact customer support."
            )
        return (
            "I couldn't find your record linked to this number. "
            "Please contact TVS Credit support or try again from your registered mobile number."
        )

    # ---- Extract customer context ----
    status = (customer.get("payment_status") or "").lower()
    emi_amount = customer.get("emi_amount")
    due_date = customer.get("due_date")

    # -------- 3) PAY / PAYMENT LINK (intent or keyword) --------
    if is_intent("PAY_INTENT") or text in ["pay", "pay now", "payment", "link"]:
        link = create_razorpay_payment_link(
            customer["name"],
            customer["phone"],
            customer["emi_amount"],
        )

        if not link:
            link = "https://example.com/demo-emi-payment"

        log_call_entry(
            customer["phone"],
            "text_pay_request",
            "link_sent" if link else "link_failed",
            payment_link=link,
            customer_id=customer["id"],
        )

        prefix = ""
        if is_negative():
            prefix = "I understand money can be stressful. "
        return f"{prefix}Hello {customer['name']}! Pay your EMI here: {link}"

    # -------- 4) STATUS (intent or keyword, typo tolerant) --------
    words = text.split()
    close_to_status = any(
        difflib.get_close_matches(w, ["status"], cutoff=0.7) for w in words
    )
    if is_intent("STATUS_QUERY") or "status" in text or close_to_status:
        msg = f"EMI status for {customer['name']}:\n"
        if emi_amount is not None:
            msg += f"- EMI Amount: ₹{emi_amount}\n"
        if due_date:
            msg += f"- Due Date: {due_date}\n"
        msg += f"- Current Status: {customer['payment_status']}"

        # 🔮 Add predicted probability (if available)
        if payment_prob is not None:
            msg += (
                f"\n- Predicted payment probability (next cycle): {payment_prob:.2f}"
            )

        return msg

    # -------- 5) WHY SHOULD I PAY (intent or text condition) --------
    if is_intent("WHY_PAY") or looks_like_why_pay(text):
        if status == "paid":
            return (
                "Our records show your EMI is already PAID. "
                "Thank you! No further payment is required."
            )

        empathy = ""
        if is_negative():
            empathy = "I understand this can feel confusing or difficult.\n"

        reason = (
            empathy
            + "This EMI is due as per your loan agreement with TVS Credit. "
            "Paying on time helps you avoid late fees and protects your credit score.\n"
        )
        if emi_amount is not None or due_date:
            reason += "\nDetails:"
            if emi_amount is not None:
                reason += f"\n- EMI Amount: ₹{emi_amount}"
            if due_date:
                reason += f"\n- Due Date: {due_date}"
        reason += "\n\nYou can type 'PAY' to get your secure payment link."
        return reason

    # -------- 6) I ALREADY PAID (intent or keywords) --------
    if is_intent("ALREADY_PAID") or looks_like_already_paid(text):
        if status == "paid":
            return (
                "Yes, our records already show this EMI as PAID. "
                "Thank you! No further action is needed."
            )
        extra = ""
        if is_negative():
            extra = "I’m sorry for the inconvenience.\n"
        return (
            extra
            + "Right now our records still show this EMI as Pending. "
            "If you have already paid, it may take some time to update from the payment gateway. "
            "You can share your payment reference with an agent, or it will auto-update "
            "once we receive confirmation from our partner."
        )

    # -------- 7) AGENT / HUMAN (intent or keywords) --------
    if (
        is_intent("AGENT_REQUEST")
        or "agent" in text
        or "human" in text
        or "call me" in text
        or "customer care" in text
    ):
        if is_angry():
            prefix = (
                "I’m sorry this experience has been frustrating. "
                "A human agent will be better able to help you.\n"
            )
        else:
            prefix = ""
        return (
            prefix
            + "Okay, we will arrange for an agent to contact you on your registered number. "
            "For urgent help, please call our customer support helpline."
        )

    # -------- 8) DOUBT / QUESTION / POLICY EXPLANATION (RAG) --------
    if (
        is_intent("DOUBT_QUERY")
        or "doubt" in text
        or "question" in text
        or "confused" in text
        or "explain" in text
        or "what is" in text
        or looks_like_question(text)  # 👈 NEW: catches "What happens if I miss my EMI due date?"
    ):
        logging.info("🧩 RAG/Policy branch triggered for: %s", text)

        # 🔍 Fetch relevant TVS policy chunks (only if RAG enabled/model loaded)
        policy_snippets = retrieve_policy_chunks(body)
        logging.info("🧩 Retrieved %d policy snippets", len(policy_snippets))

        answer = gemini_policy_answer(body, customer, extra_context=policy_snippets)
        return (
            answer
            + "\n\nIf this doesn't fully answer your question, you can type 'AGENT' to talk to a human."
        )

    # -------- 9) FALLBACK → Gemini general EMI chat --------
    answer = gemini_policy_answer(body, customer)

    if is_angry():
        return "I can see you’re upset. I’ll still try to help:\n" + answer

    return answer


def retrieve_policy_chunks(query: str, top_k: int = 5):
    """
    Given a user query, return top_k relevant policy chunks (list of strings).
    Embeddings are stored as comma-separated floats in TEXT column.
    """
    if policy_model is None:
        logging.info("Policy model not loaded or RAG disabled; skipping retrieval.")
        return []

    try:
        # Encode query
        q_emb = policy_model.encode([query])[0]  # shape (384,)
        q_norm = np.linalg.norm(q_emb) + 1e-8

        # Fetch all chunks from DB
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        cur.execute("SELECT chunk_text, embedding FROM policy_chunks")
        rows = cur.fetchall()
        cur.close()
        conn.close()

        scored = []

        for chunk_text, emb_str in rows:
            if not emb_str:
                continue
            try:
                # parse "0.1234,0.5678,..." -> numpy array
                vec = np.fromstring(emb_str, sep=",", dtype=float)
                if vec.size == 0:
                    continue

                v_norm = np.linalg.norm(vec) + 1e-8
                sim = float(np.dot(q_emb, vec) / (q_norm * v_norm))
                scored.append((sim, chunk_text))
            except Exception:
                continue

        # sort by similarity (highest first)
        scored.sort(key=lambda x: x[0], reverse=True)

        # return top_k texts
        return [t for (s, t) in scored[:top_k]]

    except Exception:
        logging.exception("Policy retrieval failed")
        return []


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
                                ["dtmf_pay_link", "sms_pay_request", "text_pay_request"]
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

        reply_text = handle_text_message(body, from_number)

        resp = MessagingResponse()
        resp.message(reply_text)
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


# ------------------ CHAT UI (Web chatbot) ------------------
CHAT_HTML = """
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8" />
  <title>TVS Mitra Chat</title>
  <style>
    body { font-family: system-ui, sans-serif; background:#f3f4f6; margin:0; padding:0; display:flex; justify-content:center; align-items:center; height:100vh;}
    .chat-container { width: 360px; max-width: 100%; background:white; border-radius:16px; box-shadow:0 10px 30px rgba(0,0,0,0.1); padding:16px; display:flex; flex-direction:column; }
    .header { font-weight:600; margin-bottom:8px; }
    #chat-log { flex:1; overflow-y:auto; border:1px solid #e5e7eb; border-radius:8px; padding:8px; margin-bottom:8px; font-size:14px; }
    .bubble { margin:4px 0; padding:6px 8px; border-radius:10px; max-width:80%; }
    .user { background:#e0f2fe; align-self:flex-end; }
    .bot { background:#f3f4f6; align-self:flex-start; }
    .input-row { display:flex; gap:8px; }
    input { flex:1; padding:6px 8px; border-radius:999px; border:1px solid #d1d5db; font-size:14px; }
    button { padding:6px 12px; border-radius:999px; border:none; background:#2563eb; color:white; font-size:14px; cursor:pointer; }
    button:disabled { opacity:0.6; cursor:default; }
  </style>
</head>
<body>
  <div class="chat-container">
    <div class="header">TVS Mitra – EMI Assistant</div>
    <div id="chat-log"></div>
    <div class="input-row">
      <input id="msg" placeholder="Type hi, pay, status, why should I pay, etc..." autocomplete="off" />
      <button id="send">Send</button>
    </div>
  </div>

<script>
const log = document.getElementById('chat-log');
const input = document.getElementById('msg');
const btn = document.getElementById('send');

// Get phone from URL: /chat?phone=+919064476365
const params = new URLSearchParams(window.location.search);
const FROM_NUMBER = params.get("phone") || "+919064476365";

function addBubble(text, who) {
  const div = document.createElement('div');
  div.className = 'bubble ' + (who === 'user' ? 'user' : 'bot');
  div.textContent = text;
  log.appendChild(div);
  log.scrollTop = log.scrollHeight;
}

async function sendMessage() {
  const text = input.value.trim();
  if (!text) return;
  addBubble(text, 'user');
  input.value = '';
  btn.disabled = true;

  try {
    const resp = await fetch('/chat-api', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ message: text, from: FROM_NUMBER })
    });
    const data = await resp.json();
    addBubble(data.reply || '(no reply)', 'bot');
  } catch (e) {
    addBubble('Error talking to server.', 'bot');
  } finally {
    btn.disabled = false;
    input.focus();
  }
}

btn.onclick = sendMessage;
input.addEventListener('keydown', e => {
  if (e.key === 'Enter') sendMessage();
});

// greeting
addBubble("Hi, I'm TVS Mitra. Type 'hi' to start or 'pay' to get your EMI payment link.", 'bot');
</script>
</body>
</html>
"""


@app.route("/chat", methods=["GET"])
def chat_page():
    return Response(CHAT_HTML, mimetype="text/html")


@app.route("/chat-api", methods=["POST"])
def chat_api():
    data = request.get_json(force=True) or {}
    body = data.get("message", "")
    from_number = data.get("from", "+919064476365")
    reply = handle_text_message(body, from_number)
    return jsonify({"reply": reply})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    logging.info(f"🚀 Starting TVS Mitra v2 on port {port}")
    app.run(host="0.0.0.0", port=port)
