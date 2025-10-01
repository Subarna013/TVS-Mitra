import os
from first_call import call_customers
from dotenv import load_dotenv

# ------------------ LOAD ENV ------------------
load_dotenv()

# ------------------ RUN DAILY ------------------
if __name__ == "__main__":
    print("Starting daily automated calls for TVS Mitra...")
    call_customers()
    print("Daily calls process completed.")
