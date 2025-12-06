# intents_inference.py
import os
import joblib

INTENT_MODEL_PATH = os.getenv("INTENT_MODEL_PATH", "intent_model.joblib")

try:
    intent_model = joblib.load(INTENT_MODEL_PATH)
    print("✅ Intent model loaded.")
except Exception as e:
    print(f"⚠️ Could not load intent model: {e}")
    intent_model = None

def predict_intent(text: str):
    """
    Returns (intent_label, confidence) for given user text.
    If model not available, returns (None, 0.0).
    """
    if not intent_model:
        return None, 0.0

    text = (text or "").strip().lower()
    if not text:
        return None, 0.0

    # get probabilities if possible
    try:
        proba = intent_model.predict_proba([text])[0]
        classes = list(intent_model.classes_)
        # pick top
        max_idx = proba.argmax()
        intent = classes[max_idx]
        confidence = float(proba[max_idx])
        return intent, confidence
    except Exception:
        # some models (like LinearSVC) don't have predict_proba
        try:
            intent = intent_model.predict([text])[0]
            # fake confidence
            return intent, 0.7
        except Exception:
            return None, 0.0
