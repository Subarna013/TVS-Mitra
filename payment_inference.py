# payment_inference.py
import os
from datetime import date, timedelta, datetime

import pandas as pd
from sqlalchemy import create_engine, MetaData, select, func, case
from dotenv import load_dotenv
import joblib

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("❌ DATABASE_URL not set in env")

engine = create_engine(DATABASE_URL)
metadata = MetaData()
metadata.reflect(bind=engine)

customers = metadata.tables["customers"]
call_logs = metadata.tables.get("call_logs")

TODAY = date.today()

# Load model + scaler (trained by payment_predict_train.py)
try:
    MODEL = joblib.load("payment_model.joblib")
    SCALER = joblib.load("payment_scaler.joblib")
    print("✅ Loaded payment_model.joblib & payment_scaler.joblib")
except Exception as e:
    print(f"⚠️ Could not load payment model/scaler: {e}")
    MODEL = None
    SCALER = None


def _get_call_stats(customer_id: int):
    """
    Get num_calls_14d and num_pay_links_14d for a single customer.
    """
    if call_logs is None:
        return 0.0, 0.0

    fourteen_days_ago = datetime.combine(
        TODAY - timedelta(days=14),
        datetime.min.time(),
    )

    with engine.connect() as conn:
        row = (
            conn.execute(
                select(
                    func.count().label("num_calls_14d"),
                    func.sum(
                        case(
                            (
                                call_logs.c.action.in_(
                                    ["dtmf_pay_link", "text_pay_request"]
                                ),
                                1,
                            ),
                            else_=0,
                        )
                    ).label("num_pay_links_14d"),
                )
                .where(
                    call_logs.c.customer_id == customer_id,
                    call_logs.c.created_at >= fourteen_days_ago,
                )
            )
            .mappings()
            .fetchone()
        )

    if not row:
        return 0.0, 0.0

    num_calls = float(row.get("num_calls_14d") or 0.0)
    num_pay_links = float(row.get("num_pay_links_14d") or 0.0)
    return num_calls, num_pay_links


def predict_payment_probability(customer: dict) -> float | None:
    """
    Given a customer row (mapping from app_v2.get_customer),
    return predicted probability of payment in next cycle (0–1),
    or None if model not available.
    """
    if MODEL is None or SCALER is None:
        return None

    # ---- Extract base fields ----
    emi_amount = customer.get("emi_amount")
    due_date = customer.get("due_date")
    payment_status = customer.get("payment_status")
    last_call_status = customer.get("last_call_status")
    risk_score = customer.get("risk_score")
    cust_id = customer.get("id")

    # ---- Feature: days_from_due ----
    if due_date is None:
        days_from_due = 0
    else:
        days_from_due = (TODAY - due_date).days
    is_overdue = int(days_from_due > 0)

    # ---- EMI amount ----
    emi_amount_float = float(emi_amount) if emi_amount is not None else 0.0

    # ---- Risk score ----
    try:
        risk_score_val = float(risk_score) if risk_score is not None else 0.5
    except Exception:
        risk_score_val = 0.5

    last_call_promise = 1 if last_call_status == "promise_to_pay" else 0

    # ---- Call stats ----
    num_calls_14d, num_pay_links_14d = _get_call_stats(cust_id)

    # ---- Build feature vector in SAME order as training ----
    feature_row = [
        emi_amount_float,
        int(days_from_due),
        is_overdue,
        risk_score_val,
        last_call_promise,
        num_calls_14d,
        num_pay_links_14d,
    ]

    X = pd.DataFrame([feature_row], columns=[
        "emi_amount_float",
        "days_from_due",
        "is_overdue",
        "risk_score_filled",
        "last_call_promise",
        "num_calls_14d",
        "num_pay_links_14d",
    ])

    X_scaled = SCALER.transform(X)
    prob = MODEL.predict_proba(X_scaled)[0, 1]
    return float(prob)
