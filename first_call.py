import os
from twilio.rest import Client
from dotenv import load_dotenv

# ------------------ LOAD ENV ------------------
load_dotenv()

account_sid = os.getenv("REMOVED")
auth_token = os.getenv("REMOVED")
twilio_number = os.getenv("TWILIO_PHONE_NUMBER")
my_number = os.getenv("MY_NUMBER")
bot_url = os.getenv("BOT_URL")  # e.g., https://tvs-mitra-1.onrender.com

if not bot_url:
    raise ValueError("Please set BOT_URL in your .env file pointing to /voice endpoint.")

# ------------------ INIT CLIENT ------------------
client = Client(account_sid, auth_token)

# ------------------ MAKE CALL ------------------
try:
    call = client.calls.create(
        to=my_number,
        from_=twilio_number,
        url=f"{bot_url}/voice"
    )
    print(f"Call initiated successfully! SID: {call.sid}")
except Exception as e:
    print(f"Failed to initiate call: {str(e)}")
