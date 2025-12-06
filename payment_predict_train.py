# payment_predict_train.py
import os
from datetime import date, timedelta, datetime

import pandas as pd
from sqlalchemy import create_engine, MetaData, select, func, case
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


def fetch_dataset():
    with engine.connect() as conn:
        rows = conn.execute(
            select(
                customers.c.id,
                customers.c.emi_amount,
                customers.c.due_date,
                customers.c.payment_status,
                customers.c.last_call_status,
                customers.c.risk_score,
            )
        ).mappings().all()

        df = pd.DataFrame(rows)
        if df.empty:
            raise RuntimeError("❌ No customers found for training!")

        # ---- Features ----
        def days_from_due(d):
            if d is None:
                return 0
            return (TODAY - d).days

        df["days_from_due"] = df["due_date"].apply(days_from_due).astype(int)
        df["is_overdue"] = (df["days_from_due"] > 0).astype(int)
        df["emi_amount_float"] = df["emi_amount"].astype(float)

        # safer risk_score handling (avoids FutureWarning)
        df["risk_score_filled"] = (
            pd.to_numeric(df["risk_score"], errors="coerce")
            .fillna(0.5)
            .astype(float)
        )

        df["last_call_promise"] = (df["last_call_status"] == "promise_to_pay").astype(
            int
        )

        # ---- Aggregate some recent call behaviour (last 14 days) ----
        if call_logs is not None:
            fourteen_days_ago = datetime.combine(
                TODAY - timedelta(days=14), datetime.min.time()
            )

            calls_query = (
                select(
                    call_logs.c.customer_id,
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
                .where(call_logs.c.created_at >= fourteen_days_ago)
                .group_by(call_logs.c.customer_id)
            )

            calls_df = pd.read_sql(calls_query, conn)

            df = df.merge(
                calls_df,
                how="left",
                left_on="id",
                right_on="customer_id",
            )
            df["num_calls_14d"] = df["num_calls_14d"].fillna(0)
            df["num_pay_links_14d"] = df["num_pay_links_14d"].fillna(0)
        else:
            df["num_calls_14d"] = 0
            df["num_pay_links_14d"] = 0

        # ---- Label: will_pay_7d (simpler demo) ----
        # 1 = Paid, 0 = Pending/other
        df["will_pay_7d"] = (df["payment_status"] == "Paid").astype(int)

        # small debug: see distribution
        print("📊 payment_status counts:", df["payment_status"].value_counts().to_dict())
        print("📊 will_pay_7d label counts:", df["will_pay_7d"].value_counts().to_dict())

        return df


def train():
    df = fetch_dataset()

    feature_cols = [
        "emi_amount_float",
        "days_from_due",
        "is_overdue",
        "risk_score_filled",
        "last_call_promise",
        "num_calls_14d",
        "num_pay_links_14d",
    ]

    X = df[feature_cols]
    y = df["will_pay_7d"]

    # need both 0 and 1 for a proper classifier
    if y.nunique() < 2:
        raise RuntimeError(
            "❌ Not enough label variety for training. Need both 0 and 1 in will_pay_7d."
        )

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.25, random_state=42, stratify=y
    )

    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    model = LogisticRegression(max_iter=1000)
    model.fit(X_train_scaled, y_train)

    y_pred_proba = model.predict_proba(X_test_scaled)[:, 1]
    auc = roc_auc_score(y_test, y_pred_proba)
    print(f"✅ Trained payment prediction model, ROC-AUC = {auc:.3f}")

    joblib.dump(model, "payment_model.joblib")
    joblib.dump(scaler, "payment_scaler.joblib")
    print("💾 Saved payment_model.joblib and payment_scaler.joblib")


if __name__ == "__main__":
    train()
