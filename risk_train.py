# risk_train.py
import os
from datetime import date, timedelta, datetime

import pandas as pd
from sqlalchemy import create_engine, MetaData, Table, select, func
from dotenv import load_dotenv

from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
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

def fetch_training_data():
    """
    Build a training dataframe from customers + aggregated call_logs.
    This is a simple heuristic setup for demo.
    """

    with engine.connect() as conn:
        # Base customer info
        rows = conn.execute(
            select(
                customers.c.id,
                customers.c.emi_amount,
                customers.c.due_date,
                customers.c.payment_status,
                customers.c.last_call_status,
            )
        ).mappings().all()

        df = pd.DataFrame(rows)

        if df.empty:
            raise RuntimeError("❌ No customers found for training!")

        # ---- Feature: days_overdue ----
        def compute_days_overdue(d):
            if d is None:
                return 0
            return max((TODAY - d).days, 0)

        df["days_overdue"] = df["due_date"].apply(compute_days_overdue)

        # ---- Feature: is_overdue ----
        df["is_overdue"] = (df["days_overdue"] > 0).astype(int)

        # ---- Feature: emi_amount_float ----
        df["emi_amount_float"] = df["emi_amount"].astype(float)

        # ---- Feature: last_call_promise ----
        df["last_call_promise"] = (df["last_call_status"] == "promise_to_pay").astype(int)

        # ---- Features from call_logs (if table exists) ----
        if call_logs is not None:
            # calls in last 30 days
            thirty_days_ago = datetime.combine(TODAY - timedelta(days=30), datetime.min.time())

            calls_df = pd.read_sql(
                select(
                    call_logs.c.customer_id,
                    func.count().label("num_calls_30d"),
                    func.sum(
                        func.case(
                            (call_logs.c.action.in_(["dtmf_pay_link", "text_pay_request"]), 1),
                            else_=0,
                        )
                    ).label("num_pay_links_30d"),
                )
                .where(call_logs.c.created_at >= thirty_days_ago)
                .group_by(call_logs.c.customer_id),
                conn,
            )

            df = df.merge(
                calls_df,
                how="left",
                left_on="id",
                right_on="customer_id",
            )
            df["num_calls_30d"] = df["num_calls_30d"].fillna(0)
            df["num_pay_links_30d"] = df["num_pay_links_30d"].fillna(0)
        else:
            df["num_calls_30d"] = 0
            df["num_pay_links_30d"] = 0

        # ---- LABEL: default_flag (for demo) ----
        # 1 = "risky" : Pending AND days_overdue >= 30
        # 0 = otherwise
        df["default_flag"] = (
            (df["payment_status"] == "Pending") & (df["days_overdue"] >= 30)
        ).astype(int)

        return df


def train_model():
    df = fetch_training_data()

    feature_cols = [
        "emi_amount_float",
        "days_overdue",
        "is_overdue",
        "last_call_promise",
        "num_calls_30d",
        "num_pay_links_30d",
    ]

    X = df[feature_cols]
    y = df["default_flag"]

    # If all labels are same, model won't train properly
    if y.nunique() < 2:
        raise RuntimeError(
            "❌ Not enough label variety for training. Need both defaulted and non-defaulted customers."
        )

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.25, random_state=42, stratify=y
    )

    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    model = LogisticRegression(max_iter=1000)
    model.fit(X_train_scaled, y_train)

    # Evaluate
    y_pred_proba = model.predict_proba(X_test_scaled)[:, 1]
    auc = roc_auc_score(y_test, y_pred_proba)
    print(f"✅ Trained risk model, ROC-AUC = {auc:.3f}")

    # Save model + scaler
    joblib.dump(model, "risk_model.joblib")
    joblib.dump(scaler, "risk_scaler.joblib")
    print("💾 Saved risk_model.joblib and risk_scaler.joblib")


if __name__ == "__main__":
    train_model()
