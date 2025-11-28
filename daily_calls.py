# daily_calls.py
import logging
from datetime import datetime, time
from dotenv import load_dotenv
from first_call import call_customers  # make sure first_call.py defines call_customers()

# ------------------ SETUP ------------------
load_dotenv()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

# Calling window (local time)
CALL_START = time(9, 0)   # 09:00
CALL_END   = time(19, 0)  # 19:00 (7 PM)

# Skip Sundays? (collections teams often do)
SKIP_SUNDAYS = True


def within_call_window():
    """Return True if current time is within allowed calling window."""
    now = datetime.now()
    now_time = now.time()

    if SKIP_SUNDAYS and now.weekday() == 6:  # Monday=0, Sunday=6
        logging.info("📵 Sunday detected and SKIP_SUNDAYS=True. No automated calls today.")
        return False

    if not (CALL_START <= now_time <= CALL_END):
        logging.info(
            f"⏱️ Outside calling window ({CALL_START.strftime('%H:%M')} - "
            f"{CALL_END.strftime('%H:%M')}). Skipping automated calls."
        )
        return False

    return True


# ------------------ RUN DAILY ------------------
if __name__ == "__main__":
    logging.info("🚀 Starting daily automated calls for TVS Mitra...")

    if not within_call_window():
        logging.info("ℹ️ Daily calls aborted due to time/day constraints.")
    else:
        try:
            call_customers()
            logging.info("✅ Daily calls process completed successfully.")
        except Exception:
            logging.exception("❌ Daily calls process failed.")
            # Let the exception propagate if you want cron/monitoring to notice
            raise
