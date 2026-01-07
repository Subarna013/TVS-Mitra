# chatbot/intents.py

from chatbot.layer1_intent import detect_intent_layer1
from chatbot.layer2_semantic_intent import detect_intent_layer2
from chatbot.layer3_llm_intent import detect_intent_layer3

import os

DEPLOY_MODE = os.getenv("DEPLOY_MODE", "full")

if DEPLOY_MODE == "full":
    from chatbot.layer1_intent import detect_intent_layer1
    from chatbot.layer2_semantic_intent import detect_intent_layer2
    from chatbot.layer3_llm_intent import detect_intent_layer3
else:
    detect_intent_layer1 = None
    detect_intent_layer2 = None
    detect_intent_layer3 = None

def detect_intent(message: str) -> str:
    if detect_intent_layer1:
        intent = detect_intent_layer1(message)
        if intent:
            return intent

    if detect_intent_layer2:
        intent = detect_intent_layer2(message)
        if intent:
            return intent

    if detect_intent_layer3:
        return detect_intent_layer3(message)

    return "unknown"
