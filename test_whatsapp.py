from twilio.rest import Client
from dotenv import load_dotenv
import os

load_dotenv()

account_sid = os.getenv("TWILIO_ACCOUNT_SID")
auth_token = os.getenv("TWILIO_AUTH_TOKEN")

client = Client(account_sid, auth_token)

TO_NUMBER = "whatsapp:+919064476365"      # your WA
FROM_NUMBER = "whatsapp:+14155238886"     # sandbox

msg = client.messages.create(
    to=TO_NUMBER,
    from_=FROM_NUMBER,
    body="Test WA from TVS Mitra ✅"
)

print("SID:", msg.sid)
