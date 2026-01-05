# chatbot/responses.py

from datetime import date

# =======================
# FORMAT HELPERS
# =======================

def _fmt_date(d):
    if not d:
        return "N/A"
    if isinstance(d, str):
        return d
    if isinstance(d, date):
        return d.strftime("%d %b %Y")
    return "N/A"


def _rupees(x):
    try:
        return f"₹{float(x):,.2f}"
    except Exception:
        return "₹N/A"


# =======================
# RESPONSE ROUTER
# =======================

def get_response(intent: str, customer: dict | None) -> str:
    """
    Rule-based, deterministic responses.
    NO LLM usage here.
    Safe for payments & compliance.
    """

    # -----------------------
    # DEFAULT VALUES
    # -----------------------
    name = customer.get("name", "Customer") if customer else "Customer"
    emi_amount = _rupees(customer.get("emi_amount")) if customer else "₹N/A"
    due_date = _fmt_date(customer.get("due_date")) if customer else "N/A"
    status = customer.get("payment_status", "Unknown") if customer else "Unknown"

    # -----------------------
    # ALREADY PAID
    # -----------------------
    if intent == "already_paid":
        if status.lower() == "paid":
            return (
                f"Thank you, {name}. Our records show that your EMI payment "
                "has already been received. No further action is required."
            )
        else:
            return (
                f"Thanks for the update, {name}. If you have already made the payment, "
                "it may take some time to reflect in our system. "
                "Please keep your payment reference handy for verification."
            )

    # -----------------------
    # PAY NOW
    # -----------------------
    if intent == "pay_now":
        if not customer:
            return (
                "I’m unable to locate your account details at the moment. "
                "Please contact TVS Credit support for assistance."
            )

        return (
            f"{name}, your EMI amount is {emi_amount} and the due date is {due_date}. "
            "You can complete the payment using the secure payment link "
            "shared with you via SMS or WhatsApp."
        )

    # -----------------------
    # STATUS
    # -----------------------
    if intent == "status":
        if not customer:
            return (
                "I’m unable to find your account details. "
                "Please check your registered phone number or contact support."
            )

        return (
            f"Here are your EMI details, {name}:\n"
            f"- EMI Amount: {emi_amount}\n"
            f"- Due Date: {due_date}\n"
            f"- Current Status: {status}"
        )

    # -----------------------
    # WHY PAY
    # -----------------------
    if intent == "why_pay":
        return (
            "EMI payments help keep your loan account in good standing. "
            "Timely payments help avoid late charges and ensure uninterrupted services."
        )

    # -----------------------
    # FALLBACK
    # -----------------------
    return (
        "I can help you with EMI-related questions such as payment status, "
        "payment process, or general clarifications. "
        "Could you please rephrase your question?"
    )
