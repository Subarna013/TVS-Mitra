# message.py
from twilio.rest import Client
import os
from dotenv import load_dotenv

# Load .env variables
load_dotenv()

account_sid = os.getenv("TWILIO_ACCOUNT_SID")
auth_token = os.getenv("TWILIO_AUTH_TOKEN")
twilio_number = os.getenv("TWILIO_PHONE_NUMBER")

# Your verified test number
my_number = "+919064476365"

if not account_sid or not auth_token or not twilio_number:
    raise RuntimeError("❌ Missing Twilio credentials in .env file!")

client = Client(account_sid, auth_token)

try:
    message = client.messages.create(
        to=my_number,
        from_=twilio_number,
        body="Test message from TVS Mitra!"
    )
    print("✅ SMS sent successfully!")
    print("SID:", message.sid)

except Exception as e:
    print("❌ Failed to send SMS:", e)
