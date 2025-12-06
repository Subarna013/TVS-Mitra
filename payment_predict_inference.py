# payment_predict_inference.py
import os
from datetime import date
import numpy as np
import joblib

TODAY = date.today()

PAYMENT_MODEL_PATH = os.getenv("PAYMENT_MODEL_PATH", "payment_model.joblib")
PAYMENT_SCALER_PATH = os.getenv("PAYMENT_SCALER_PATH", "payment_scaler.joblib")

try:
    payment_model = joblib.load(PAYMENT_MODEL_PATH)
    payment_scaler = joblib.load(PAYMENT_SCALER_PATH)
    print("✅ Payment prediction model loaded.")
except Exception as e:
    print(f"⚠️ Could not load payment model/scaler: {e}")
    payment_model = None
    payment_scaler = None

def build_features(cust_row):
    emi_amount = float(cust_row.emi_amount)

    if cust_row.due_date:
        days_from_due = (TODAY - cust_row.due_date).days
    else:
        days_from_due = 0

    is_overdue = 1 if days_from_due > 0 else 0
    risk_score = float(getattr(cust_row, "risk_score", 0.5) or 0.5)
    last_call_promise = 1 if getattr(cust_row, "last_call_status", None) == "promise_to_pay" else 0

    # For live scoring, we may not recompute recent call counts → set 0 or pass separately
    num_calls_14d = 0
    num_pay_links_14d = 0

    arr = np.array(
        [
            emi_amount,
            days_from_due,
            is_overdue,
            risk_score,
            last_call_promise,
            num_calls_14d,
            num_pay_links_14d,
        ]
    ).reshape(1, -1)
    return arr

def predict_payment_probability(cust_row):
    """
    Returns probability in [0,1] that this customer will pay within ~7 days.
    Fallback 0.5 if model not loaded.
    """
    if payment_model is None or payment_scaler is None:
        return 0.5

    X = build_features(cust_row)
    X_scaled = payment_scaler.transform(X)
    proba = float(payment_model.predict_proba(X_scaled)[0, 1])
    return proba
