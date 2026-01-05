# chatbot/llm.py

import os
import google.generativeai as genai

# =======================
# GEMINI SETUP
# =======================

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

model = genai.GenerativeModel(
    model_name="gemini-1.5-flash"
)

# =======================
# SYSTEM PROMPT (STRICT + SAFE)
# =======================

SYSTEM_PROMPT = """
You are TVS Mitra, a professional EMI support assistant for TVS Credit.

Your role:
- Explain EMI-related questions clearly and politely
- Use ONLY the policy information provided below
- Use customer details ONLY as reference (do not infer new facts)

STRICT RULES:
- Do NOT ask the customer to pay
- Do NOT generate payment links
- Do NOT promise waivers, discounts, or approvals
- Do NOT give legal advice
- Do NOT guess if policy information is missing
- If policy info is insufficient, say you will connect to support
- Keep responses short and clear (max 3–5 lines)
"""

# =======================
# RESPONSE GENERATOR
# =======================

def generate_llm_reply(
    user_message: str,
    policy_context: str | None,
    customer: dict | None
) -> str:
    """
    Explanation-only response generator.
    Used ONLY after intent is known.
    """

    if not user_message or not user_message.strip():
        return "I didn’t catch that. Could you please rephrase your question?"

    # -----------------------
    # Customer context (read-only)
    # -----------------------

    customer_block = ""
    if customer:
        customer_block = f"""
Customer reference details (read-only):
- Name: {customer.get("name", "Customer")}
- EMI Amount: {customer.get("emi_amount", "N/A")}
- Due Date: {customer.get("due_date", "N/A")}
- Payment Status: {customer.get("payment_status", "Unknown")}
"""

    # -----------------------
    # Policy context (MANDATORY)
    # -----------------------

    if not policy_context:
        return (
            "I don’t have enough policy information to answer that accurately. "
            "I’ll connect you with TVS Credit support for further help."
        )

    policy_block = f"""
Policy information (authoritative source):
{policy_context}
"""

    # -----------------------
    # Final prompt
    # -----------------------

    prompt = f"""
{SYSTEM_PROMPT}

{customer_block}

{policy_block}

User question:
{user_message}

Respond clearly and politely using ONLY the policy information above.
"""

    try:
        response = model.generate_content(
            prompt,
            generation_config={
                "temperature": 0.2,
                "max_output_tokens": 180
            }
        )

        return (response.text or "").strip()

    except Exception:
        return (
            "I’m unable to answer that right now. "
            "Please contact TVS Credit support for further assistance."
        )
