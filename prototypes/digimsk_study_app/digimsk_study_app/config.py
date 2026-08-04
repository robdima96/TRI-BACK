"""Study app environment configuration."""

from __future__ import annotations

import os
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_DATA = _ROOT / "data"


def _default_sessions_dir() -> Path:
    """Local monorepo: ../../bot/data/sessions. Container: data/sessions under app root."""
    try:
        return _ROOT.parents[1] / "bot" / "data" / "sessions"
    except IndexError:
        return _DATA / "sessions"


try:
    from dotenv import load_dotenv

    load_dotenv(_ROOT / ".env", override=False)
except ImportError:
    pass


def _env_str(key: str, default: str) -> str:
    val = os.getenv(key, default).strip()
    return val or default


def _env_int(key: str, default: int) -> int:
    raw = os.getenv(key, str(default)).strip()
    try:
        return int(raw)
    except ValueError:
        return default


def _env_bool(key: str, default: bool = False) -> bool:
    raw = os.getenv(key, "").strip().lower()
    if raw in ("1", "true", "yes", "on"):
        return True
    if raw in ("0", "false", "no", "off"):
        return False
    return default


STUDY_DB_PATH = Path(_env_str("DIGIMSK_STUDY_DB", str(_DATA / "digimsk.db")))
SESSIONS_DIR = Path(_env_str("DIGIMSK_SESSIONS_DIR", str(_default_sessions_dir())))
CHATBOT_BASE_URL = _env_str("CHATBOT_BASE_URL", "http://127.0.0.1:8001").rstrip("/")
# Same secret as bot ``DIGIMSK_BOT_API_KEY``; empty = no Authorization header (local).
BOT_API_KEY = (os.getenv("DIGIMSK_BOT_API_KEY") or "").strip()
TRAVERSAL_MODE = _env_str("TRAVERSAL_MODE", "bot")
IDLE_TIMEOUT_SEC = _env_int("IDLE_TIMEOUT_SEC", 60)
MAX_STORED_MESSAGES = 40
LOGIN_RATE_LIMIT = 8
LOGIN_RATE_WINDOW_SEC = 300

PUBLIC_ACCESS = _env_bool("DIGIMSK_PUBLIC_ACCESS", False)
PUBLIC_BASE_URL = _env_str("DIGIMSK_PUBLIC_BASE_URL", "").rstrip("/")
# 7 days local; 12 hours when public HTTPS share link is active.
SESSION_COOKIE_MAX_AGE = 12 * 60 * 60 if PUBLIC_ACCESS else 7 * 24 * 60 * 60

if PUBLIC_ACCESS and not BOT_API_KEY:
    raise RuntimeError(
        "DIGIMSK_PUBLIC_ACCESS=1 requires DIGIMSK_BOT_API_KEY "
        "(study UI must authenticate to the bot API)."
    )
