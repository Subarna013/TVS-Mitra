# chatbot/layer3_llm_intent.py

import os
import google.generativeai as genai

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

model = genai.GenerativeModel(
    model_name="gemini-1.5-flash"
)

ALLOWED_INTENTS = {
    "already_paid",
    "pay_now",
    "status",
    "why_pay",
    "unknown",
}

SYSTEM_PROMPT = """
You are an intent classifier for a banking EMI collections chatbot.

Classify the user's message into EXACTLY ONE of these labels:
already_paid
pay_now
status
why_pay
unknown

Rules:
- Return ONLY the label
- No explanations
- No punctuation
- No extra words
- If unclear or mixed, return "unknown"
"""

def detect_intent_layer3(message: str) -> str:
    if not message or not message.strip():
        return "unknown"

    try:
        prompt = f"""
{SYSTEM_PROMPT}

User message:
{message.strip()}
"""

        response = model.generate_content(
            prompt,
            generation_config={
                "temperature": 0.0,
                "max_output_tokens": 5,
            }
        )

        intent = (response.text or "").strip().lower()
        return intent if intent in ALLOWED_INTENTS else "unknown"

    except Exception:
        return "unknown"
