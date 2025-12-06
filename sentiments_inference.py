# sentiments_inference.py
import os
import joblib

SENTIMENT_MODEL_PATH = os.getenv("SENTIMENT_MODEL_PATH", "sentiment_model.joblib")

try:
    sentiment_model = joblib.load(SENTIMENT_MODEL_PATH)
    print("✅ Sentiment model loaded.")
except Exception as e:
    print(f"⚠️ Could not load sentiment model: {e}")
    sentiment_model = None

def predict_sentiment(text: str):
    """
    Returns (sentiment_label, confidence) for given user text.
    Labels: ANGRY, NEGATIVE, NEUTRAL, POSITIVE
    If model not available, returns (None, 0.0).
    """
    if not sentiment_model:
        return None, 0.0

    text = (text or "").strip().lower()
    if not text:
        return None, 0.0

    try:
        proba = sentiment_model.predict_proba([text])[0]
        classes = list(sentiment_model.classes_)
        max_idx = proba.argmax()
        label = classes[max_idx]
        confidence = float(proba[max_idx])
        return label, confidence
    except Exception:
        try:
            label = sentiment_model.predict([text])[0]
            return label, 0.7
        except Exception:
            return None, 0.0
