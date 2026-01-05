# chatbot/chatbot_api.py

from chatbot.intents import detect_intent
from chatbot.responses import get_response
from chatbot.rag import fetch_policy_context
from chatbot.llm import generate_llm_reply
from chatbot.memory import get_context, update_context
from db.db import get_customer


def handle_chat_message(message: str, phone: str) -> str:
    # Fetch customer data
    customer = get_customer(phone)

    # Detect intent (Layer 1 → Layer 2 → Layer 3)
    intent = detect_intent(message)

    # Load memory (optional but good practice)
    context = get_context(phone)

    # 🔐 MONEY-SAFE ROUTING (THIS IS THE CRITICAL PART)
    if intent in ["already_paid", "pay_now", "status", "why_pay"]:
        reply = get_response(intent, customer)
    else:
        policy_text = fetch_policy_context(message)
        reply = generate_llm_reply(
            user_message=message,
            policy_context=policy_text,
            customer=customer
        )

    # Update conversation memory
    update_context(phone, intent)

    return reply
