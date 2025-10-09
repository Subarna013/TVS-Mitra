# daily_calls.py
import os
import logging
from dotenv import load_dotenv
from first_call import call_customers   # make sure first_call.py defines call_customers()

# ------------------ SETUP ------------------
load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# ------------------ RUN DAILY ------------------
if __name__ == "__main__":
    logging.info("🚀 Starting daily automated calls for TVS Mitra...")
    try:
        call_customers()
        logging.info("✅ Daily calls process completed successfully.")
    except Exception as e:
        logging.exception("❌ Daily calls process failed.")
        raise e
