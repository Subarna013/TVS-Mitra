# risk_inference.py
import os
from datetime import date
import joblib
import numpy as np

RISK_MODEL_PATH = os.getenv("RISK_MODEL_PATH", "risk_model.joblib")
RISK_SCALER_PATH = os.getenv("RISK_SCALER_PATH", "risk_scaler.joblib")

TODAY = date.today()

try:
    model = joblib.load(RISK_MODEL_PATH)
    scaler = joblib.load(RISK_SCALER_PATH)
    print("✅ Risk model & scaler loaded.")
except Exception as e:
    print(f"⚠️ Could not load risk model/scaler: {e}")
    model = None
    scaler = None


def compute_features_for_customer(cust_row, num_calls_30d=0, num_pay_links_30d=0):
    """
    cust_row: a SQLAlchemy row or dict-like with keys:
      emi_amount, due_date, payment_status, last_call_status
    """
    emi_amount = float(cust_row.emi_amount)

    if cust_row.due_date:
        days_overdue = max((TODAY - cust_row.due_date).days, 0)
    else:
        days_overdue = 0

    is_overdue = 1 if days_overdue > 0 else 0
    last_call_promise = 1 if getattr(cust_row, "last_call_status", None) == "promise_to_pay" else 0

    features = np.array(
        [
            emi_amount,
            days_overdue,
            is_overdue,
            last_call_promise,
            num_calls_30d,
            num_pay_links_30d,
        ]
    ).reshape(1, -1)

    return features


def score_customer_risk(cust_row, num_calls_30d=0, num_pay_links_30d=0):
    """
    Returns (risk_score, risk_bucket).
    If model not loaded, returns (0.5, 'MEDIUM') as fallback.
    """
    if model is None or scaler is None:
        return 0.5, "MEDIUM"

    X = compute_features_for_customer(cust_row, num_calls_30d, num_pay_links_30d)
    X_scaled = scaler.transform(X)
    proba = model.predict_proba(X_scaled)[0, 1]  # P(default = 1)

    # Bucket logic (you can tweak thresholds)
    if proba >= 0.7:
        bucket = "HIGH"
    elif proba >= 0.4:
        bucket = "MEDIUM"
    else:
        bucket = "LOW"

    return float(proba), bucket
