# chatbot/memory.py

from datetime import datetime, timedelta
from typing import Dict, Any

# =======================
# CONFIG
# =======================

MEMORY_TTL_MINUTES = 30  # auto-expire inactive chats

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

_memory_store: Dict[str, Dict[str, Any]] = {}

# =======================
# INTERNAL HELPERS
# =======================

def _is_expired(entry: dict) -> bool:
    return (
        datetime.utcnow() - entry.get("updated_at", datetime.utcnow())
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
    Fetch conversation context for a user.
    Returns empty dict if not found or expired.
    """

    if not phone:
        return {}

    _cleanup(phone)
    return _memory_store.get(phone, {}).copy()

def update_context(phone: str, intent: str | None, message: str | None = None):
    """
    Update conversation memory.
    Stores only minimal, safe info.
    """

    if not phone:
        return

    _memory_store[phone] = {
        "last_intent": intent,
        "last_message": message,
        "updated_at": datetime.utcnow(),
    }

def clear_context(phone: str):
    """
    Manually clear a user's memory.
    Useful after payment completion or agent handoff.
    """

    if phone in _memory_store:
        del _memory_store[phone]
