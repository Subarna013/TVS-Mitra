# chatbot/intents/layer1_intent.py

import re
from difflib import SequenceMatcher
from collections import defaultdict
import joblib

# =======================
# NORMALIZATION
# =======================

def normalize(text: str) -> list[str]:
    """
    Lowercase, remove punctuation, normalize spaces.
    Returns list of tokens.
    """
    text = (text or "").lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text.split()


def fuzzy(a: str, b: str) -> float:
    """Fuzzy similarity between two tokens."""
    return SequenceMatcher(None, a, b).ratio()


# =======================
# NEGATION HANDLING
# =======================

NEGATIONS = {
    "not", "no", "never", "didnt", "didn't",
    "failed", "unsuccessful", "pending",
    "cancelled", "canceled", "reversed",
}

def has_negation(tokens: list[str], index: int, window: int = 3) -> bool:
    """
    Detect negation near a signal word.
    """
    start = max(0, index - window)
    end = min(len(tokens), index + window + 1)
    return any(t in NEGATIONS for t in tokens[start:end])


# =======================
# INTENT SIGNALS (RULES)
# =======================

INTENT_SIGNALS = {
    "already_paid": {
        "verbs": ["pay", "paid", "done", "complete", "clear"],
        "objects": ["emi", "payment", "amount", "money"],
        "hinglish": ["ho", "gaya", "kar", "diya"],
        "weight": 1.3,   # stricter intent
    },
    "pay_now": {
        "verbs": ["pay", "make", "do"],
        "objects": ["emi", "payment", "link"],
        "hinglish": ["bhejo", "karna"],
        "weight": 1.1,
    },
    "status": {
        "verbs": ["check", "know", "tell", "see"],
        "objects": ["status", "emi", "due", "loan"],
        "hinglish": ["batao", "kya"],
        "weight": 1.0,
    },
    "why_pay": {
        "verbs": ["why", "should"],
        "objects": ["pay", "payment", "emi"],
        "hinglish": [],
        "weight": 0.9,
    },
}

# Minimum confidence required per intent
MIN_CONFIDENCE = {
    "already_paid": 2.2,  # high-risk → strict
    "pay_now": 2.0,
    "status": 1.8,
    "why_pay": 1.5,
}


# =======================
# RULE-BASED SCORING
# =======================

def rule_score(tokens: list[str]) -> dict[str, float]:
    """
    Compute rule-based intent scores.
    """
    scores = defaultdict(float)

    for intent, cfg in INTENT_SIGNALS.items():
        for i, token in enumerate(tokens):

            # Verb signals (strong)
            for v in cfg["verbs"]:
                if fuzzy(token, v) > 0.85 and not has_negation(tokens, i):
                    scores[intent] += 1.0

            # Object signals (medium)
            for o in cfg["objects"]:
                if fuzzy(token, o) > 0.85:
                    scores[intent] += 0.7

            # Hinglish signals (light)
            for h in cfg["hinglish"]:
                if fuzzy(token, h) > 0.85:
                    scores[intent] += 0.3

        scores[intent] *= cfg["weight"]

    return scores


# =======================
# OPTIONAL ML FALLBACK (CHAR N-GRAM)
# =======================

try:
    vectorizer = joblib.load("layer1_vectorizer.joblib")
    model = joblib.load("layer1_intent_model.joblib")
    ML_ENABLED = True
except Exception:
    ML_ENABLED = False


def ml_intent(text: str) -> str | None:
    """
    Lightweight ML fallback (still Layer-1).
    """
    if not ML_ENABLED or not text:
        return None

    X = vectorizer.transform([text.lower()])
    probs = model.predict_proba(X)[0]
    idx = probs.argmax()

    return model.classes_[idx] if probs[idx] >= 0.85 else None


# =======================
# FINAL LAYER-1 ENTRY
# =======================

def detect_intent_layer1(message: str) -> str | None:
    """
    Returns intent if confidence is strong.
    Otherwise returns None → Layer-2.
    """
    tokens = normalize(message)
    if not tokens:
        return None

    # 1️⃣ Rule-based detection (highest trust)
    scores = rule_score(tokens)
    if scores:
        intent, confidence = max(scores.items(), key=lambda x: x[1])
        if confidence >= MIN_CONFIDENCE.get(intent, 2.0):
            return intent

    # 2️⃣ ML fallback (still deterministic, still Layer-1)
    return ml_intent(message)
