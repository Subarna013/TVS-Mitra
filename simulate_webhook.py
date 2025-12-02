import requests
import json
import os
from dotenv import load_dotenv

load_dotenv()

BOT_URL = os.getenv("BOT_URL")  # e.g. https://tvs-mitra-1.onrender.com
WEBHOOK_SECRET = os.getenv("RAZORPAY_WEBHOOK_SECRET")

if not BOT_URL:
    raise RuntimeError("❌ BOT_URL missing in .env")
if not WEBHOOK_SECRET:
    raise RuntimeError("❌ RAZORPAY_WEBHOOK_SECRET missing in .env")

# Fake webhook payload
data = {
    "event": "payment_link.paid",
    "payload": {
        "payment_link": {
            "entity": {
                "id": "plink_test_123456",
                "customer": {
                    "contact": "+919064476365"
                }
            }
        }
    }
}

# Razorpay signature simulation
import hmac, hashlib

body = json.dumps(data).encode()
signature = hmac.new(WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()

headers = {
    "Content-Type": "application/json",
    "X-Razorpay-Signature": signature
}

url = f"{BOT_URL}/razorpay/webhook"

print(f"📤 Sending simulated webhook to {url}")
response = requests.post(url, headers=headers, data=json.dumps(data))

print(f"📥 Response: {response.status_code}")
print(response.text)
