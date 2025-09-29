from twilio.rest import Client
import os
from dotenv import load_dotenv

load_dotenv()

account_sid = os.getenv("REMOVED")
auth_token = os.getenv("REMOVED")
twilio_number = os.getenv("TWILIO_PHONE_NUMBER")
my_number = "+919064476365"  # your personal verified number

client = Client(account_sid, auth_token)

message = client.messages.create(
    to=my_number,
    from_=twilio_number,
    body="Test message from TVS Mitra!"
)

print("SMS sent, SID:", message.sid)
