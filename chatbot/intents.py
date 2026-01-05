# chatbot/intents.py

from chatbot.layer1_intent import detect_intent_layer1
from chatbot.layer2_semantic_intent import detect_intent_layer2
from chatbot.layer3_llm_intent import detect_intent_layer3


def detect_intent(message: str) -> str:
    """
    Final intent detector.
    Order is CRITICAL.
    """

    # -----------------------
    # LAYER 1: Rules + ML
    # -----------------------
    intent = detect_intent_layer1(message)
    if intent:
        return intent

    # -----------------------
    # LAYER 2: Semantic NLP
    # -----------------------
    intent = detect_intent_layer2(message)
    if intent:
        return intent

    # -----------------------
    # LAYER 3: Gemini (classifier only)
    # -----------------------
    return detect_intent_layer3(message)
