# intents_train.py
import joblib
from sklearn.pipeline import Pipeline
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression

# --------- 1. Define intents + example phrases ----------

INTENT_EXAMPLES = {
    "GREET": [
        "hi", "hello", "hey", "good morning", "good evening", "namaste",
        "hi tvs", "hello mitra", "hey there"
    ],
    "HELP_MENU": [
        "help", "options", "what can you do", "menu",
        "show commands", "what are the options"
    ],
    "PAY_INTENT": [
        "i want to pay", "pay now", "payment", "send payment link",
        "pay emi", "pay my loan", "how to pay", "give me link", "upi link",
        "i want to clear my emi", "share payment link", "payment please"
    ],
    "STATUS_QUERY": [
        "what is my emi status", "status", "due amount", "how much i need to pay",
        "when is my due date", "emi details", "pending amount", "remaining emi",
        "check my emi", "show my loan status", "loan status", "emi balance"
    ],
    "WHY_PAY": [
        "why should i pay", "why i need to pay", "why this emi",
        "why are you calling", "why is this amount", "why do i owe",
        "why is emi due", "why is this payment required"
    ],
    "ALREADY_PAID": [
        "i already paid", "i have paid", "payment done", "i did the payment",
        "i paid yesterday", "money already sent", "i have already cleared",
        "i already made the payment"
    ],
    "AGENT_REQUEST": [
        "call me", "talk to human", "want to talk to agent",
        "customer care", "connect to executive", "need agent", "human support",
        "speak to someone", "talk to person"
    ],
    "DOUBT_QUERY": [
        "i have a doubt", "i have a question", "i am confused",
        "can you explain", "i have confusion", "i dont understand",
        "please clarify", "need explanation", "explain emi"
    ],
    "SMALL_TALK": [
        "how are you", "who are you", "what is your name",
        "tell me a joke", "tell me something", "what can you do for me",
        "where are you from", "are you real", "are you a robot"
    ],
    "OTHER": [
        "random text", "lorem ipsum", "bla bla", "nothing", "ignore this",
        "test message", "checking only"
    ],
}

def build_dataset():
    texts = []
    labels = []

    for intent, examples in INTENT_EXAMPLES.items():
        for ex in examples:
            texts.append(ex.lower())
            labels.append(intent)

    return texts, labels

def train_intent_model():
    texts, labels = build_dataset()

    # Tfidf + Logistic Regression pipeline
    pipeline = Pipeline(
        [
            ("tfidf", TfidfVectorizer(ngram_range=(1, 2), min_df=1)),
            ("clf", LogisticRegression(max_iter=1000)),
        ]
    )

    pipeline.fit(texts, labels)
    print("✅ Intent model trained on", len(texts), "examples.")

    joblib.dump(pipeline, "intent_model.joblib")
    print("💾 Saved intent_model.joblib")

if __name__ == "__main__":
    train_intent_model()
