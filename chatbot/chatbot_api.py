# chatbot/chatbot_api.py

from chatbot.layer1_intent import detect_intent_layer1
from chatbot.layer2_semantic_intent import detect_intent_layer2
from chatbot.layer3_llm_intent import detect_intent_layer3
from chatbot.intent_router import detect_intent

from chatbot.responses import get_response
from chatbot.rag import fetch_policy_context
from chatbot.llm import generate_llm_reply
from chatbot.memory import get_context, update_context

from db.db import get_customer


# =======================
# MASTER INTENT ROUTER
# =======================

def detect_intent(message: str) -> str:
    """
    Hybrid intent detection:
    Layer 1 → Rules + ML
    Layer 2 → Semantic similarity
    Layer 3 → Gemini (classification only)
    """

    # Layer 1 (fastest, safest)
    intent = detect_intent_layer1(message)
    if intent:
        return intent

    # Layer 2 (semantic meaning)
    intent = detect_intent_layer2(message)
    if intent:
        return intent

    # Layer 3 (LLM fallback – classification only)
    return detect_intent_layer3(message)


# =======================
# CHAT ENTRY POINT
# =======================

def handle_chat_message(message: str, phone: str) -> str:
    """
    Main chatbot handler.
    This is the ONLY function app_v2.py should call.
    """

    # Fetch customer (can be None for unknown numbers)
    customer = get_customer(phone)

    # Conversation memory (optional but useful)
    context = get_context(phone)

    # Detect intent safely
    intent = detect_intent(message)

    # -----------------------
    # 🔐 MONEY-SAFE ROUTING
    # -----------------------
    # No LLM is allowed to:
    # - ask for payment
    # - generate payment links
    # - confirm payment
    # These are rule-based ONLY
    if intent in ["already_paid", "pay_now", "status", "why_pay"]:
        reply = get_response(intent, customer)

    else:
        # Explanation / clarification only (RAG + LLM)
        policy_text = fetch_policy_context(message)

        reply = generate_llm_reply(
            user_message=message,
            policy_context=policy_text,
            customer=customer,
        )

    # Update memory (store last intent, turn count, etc.)
    update_context(phone, intent)

    return reply

