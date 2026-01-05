# chatbot/memory.py

from datetime import datetime, timedelta

# =======================
# CONFIG
# =======================

MEMORY_TTL_MINUTES = 30   # auto-expire after inactivity

# =======================
# IN-MEMORY STORE
# =======================

# Structure:
# {
#   phone: {
#       "last_intent": str,
#       "last_message": str,
#       "updated_at": datetime
#   }
# }

_memory_store: dict[str, dict] = {}

# =======================
# HELPERS
# =======================

def _is_expired(entry: dict) -> bool:
    return (
        datetime.utcnow() - entry["updated_at"]
        > timedelta(minutes=MEMORY_TTL_MINUTES)
    )

def _cleanup(phone: str):
    entry = _memory_store.get(phone)
    if entry and _is_expired(entry):
        del _memory_store[phone]

# =======================
# PUBLIC API
# =======================

def get_context(phone: str) -> dict:
    """
    Returns conversation context for the user.
    If expired or missing, returns empty context.
    """

    if not phone:
        return {}

    _cleanup(phone)
    return _memory_store.get(phone, {}).copy()

def update_context(phone: str, intent: str | None, message: str | None = None):
    """
    Updates memory with latest intent and message.
    """

    if not phone:
        return

    _memory_store[phone] = {
        "last_intent": intent,
        "last_message": message,
        "updated_at": datetime.utcnow()
    }

def clear_context(phone: str):
    """
    Clears memory for a user (manual reset).
    """
    if phone in _memory_store:
        del _memory_store[phone]
