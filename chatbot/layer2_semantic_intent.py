from sentence_transformers import SentenceTransformer, util

# =======================
# MODEL (FAST + RELIABLE)
# =======================

_model = None

def get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer("all-MiniLM-L6-v2")
    return _model


# =======================
# CANONICAL INTENTS
# =======================

INTENT_CANONICAL = {
    "already_paid": [
        "I have already paid the EMI",
        "Payment is completed",
        "EMI paid earlier",
        "Money already sent",
        "I paid yesterday",
        "Why are you calling after payment",
        "Payment done from my side",
    ],
    "pay_now": [
        "I want to pay my EMI",
        "Send payment link",
        "How can I pay",
        "I want to clear my dues",
        "Help me pay EMI",
    ],
    "status": [
        "What is my EMI status",
        "Is my EMI due",
        "Check my loan status",
        "How much do I need to pay",
        "What is the outstanding amount",
    ],
    "why_pay": [
        "Why should I pay",
        "Why do I need to pay EMI",
        "Why is payment required",
        "Why are you asking me to pay",
    ],
}

# =======================
# PRE-COMPUTE EMBEDDINGS
# =======================

INTENT_EMBS = {
    intent: _model.encode(examples, convert_to_tensor=True)
    for intent, examples in INTENT_CANONICAL.items()
}

# =======================
# LAYER-2 DETECTOR
# =======================

def detect_intent_layer2(message: str) -> str | None:
    """
    Semantic intent detection using sentence embeddings.

    Returns:
        intent (str) if confidence is strong
        None if unclear → go to Layer-3
    """

    if not message or not message.strip():
        return None

    # Encode user message
    msg_emb = _model.encode(message, convert_to_tensor=True)

    # Compute similarity scores
    scores = {}
    for intent, emb_matrix in INTENT_EMBS.items():
        score = util.cos_sim(msg_emb, emb_matrix).max().item()
        scores[intent] = score

    # Get best & second-best
    intent, best_score = max(scores.items(), key=lambda x: x[1])
    sorted_scores = sorted(scores.values(), reverse=True)

    # Safety: ensure at least 2 intents exist
    second_best = sorted_scores[1] if len(sorted_scores) > 1 else 0.0

    # Confidence + margin check
    if best_score >= 0.65 and (best_score - second_best) >= 0.05:
        return intent

    return None

