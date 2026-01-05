# chatbot/responses.py

from datetime import date

# =======================
# HELPERS
# =======================

def _fmt_date(d):
    if not d:
        return "N/A"
    if isinstance(d, str):
        return d
    return d.strftime("%d %b %Y")

def _rupees(x):
    try:
        return f"₹{float(x):,.2f}"
    except Exception:
        return "₹N/A"

# =======================
# MAIN RESPONSE ROUTER
# =======================

def get_response(intent: str, customer: dict | None) -> str:
    """
    Deterministic, rule-based responses.
    NO LLM USAGE HERE.
    """

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
                f"Thanks {name}, we can see that your EMI has already been received. "
                "No further action is required from your side."
            )
        else:
            return (
                f"Thanks for letting us know, {name}. "
                "If you’ve already made the payment, it may take some time to reflect. "
                "Please keep the payment reference handy. Our team will verify it."
            )

    # -----------------------
    # PAY NOW
    # -----------------------
    if intent == "pay_now":
        return (
            f"{name}, your EMI amount is {emi_amount} with due date {due_date}. "
            "You can complete the payment using the secure link we shared earlier."
        )

    # -----------------------
    # STATUS
    # -----------------------
    if intent == "status":
        return (
            f"Here is your EMI status, {name}:\n"
            f"- Amount: {emi_amount}\n"
            f"- Due date: {due_date}\n"
            f"- Current status: {status}"
        )

    # -----------------------
    # WHY PAY
    # -----------------------
    if intent == "why_pay":
        return (
            "EMI payments help keep your loan account in good standing. "
            "Timely payments avoid late charges and ensure uninterrupted service."
        )

    # -----------------------
    # UNKNOWN / FALLBACK
    # -----------------------
    return (
        "I’m here to help with EMI-related questions like payment status, "
        "payment process, or clarifications. Could you please rephrase your query?"
    )
