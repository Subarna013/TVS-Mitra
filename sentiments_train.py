# sentiments_train.py
import joblib
from sklearn.pipeline import Pipeline
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression

# --------- Sentiment classes & example phrases ----------

SENTIMENT_EXAMPLES = {
    "ANGRY": [
        "stop calling me",
        "dont call me again",
        "you people are harassing me",
        "this is harassment",
        "i will complain to police",
        "you are cheating me",
        "this is fraud",
        "i am very angry",
        "why are you disturbing me",
        "stop disturbing me",
        "i am frustrated",
        "leave me alone",
    ],
    "NEGATIVE": [
        "i am not happy",
        "this is not fair",
        "charges are too high",
        "i cannot pay",
        "i lost my job",
        "i am facing financial issues",
        "this is difficult for me",
        "i have a problem with this emi",
        "i am not satisfied",
    ],
    "NEUTRAL": [
        "what is my emi",
        "tell me my due date",
        "how much do i have to pay",
        "send payment link",
        "call me later",
        "i want to know my status",
        "please explain emi",
        "who are you",
        "what is this about",
        "why are you calling",
    ],
    "POSITIVE": [
        "thank you",
        "thanks for reminder",
        "ok i will pay",
        "i will pay tomorrow",
        "this is helpful",
        "good service",
        "nice reminder",
        "appreciate your help",
        "okay i understand",
    ],
}

def build_dataset():
    texts = []
    labels = []
    for label, examples in SENTIMENT_EXAMPLES.items():
        for ex in examples:
            texts.append(ex.lower())
            labels.append(label)
    return texts, labels

def train_sentiment_model():
    texts, labels = build_dataset()

    pipeline = Pipeline(
        [
            ("tfidf", TfidfVectorizer(ngram_range=(1, 2), min_df=1)),
            ("clf", LogisticRegression(max_iter=1000)),
        ]
    )

    pipeline.fit(texts, labels)
    print("✅ Sentiment model trained on", len(texts), "examples.")

    joblib.dump(pipeline, "sentiment_model.joblib")
    print("💾 Saved sentiment_model.joblib")

if __name__ == "__main__":
    train_sentiment_model()
