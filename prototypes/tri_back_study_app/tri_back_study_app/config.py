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


def env_candidates(name: str) -> tuple[str, ...]:
    return (name,)


def env_lookup(name: str) -> str | None:
    for key in env_candidates(name):
        raw = os.environ.get(key)
        if raw is not None and raw.strip() != "":
            return raw.strip()
    return None


def _env_str(key: str, default: str) -> str:
    val = env_lookup(key)
    if val:
        return val
    return default


def _env_int(key: str, default: int) -> int:
    raw = env_lookup(key)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_bool(key: str, default: bool = False) -> bool:
    raw = (env_lookup(key) or "").strip().lower()
    if raw in ("1", "true", "yes", "on"):
        return True
    if raw in ("0", "false", "no", "off"):
        return False
    return default


def _default_study_db() -> Path:
    return _DATA / "tri_back.db"


STUDY_DB_PATH = Path(_env_str("TRI_BACK_STUDY_DB", str(_default_study_db())))
SESSIONS_DIR = Path(_env_str("TRI_BACK_SESSIONS_DIR", str(_default_sessions_dir())))
CHATBOT_BASE_URL = _env_str("CHATBOT_BASE_URL", "http://127.0.0.1:8001").rstrip("/")
# Same secret as bot ``TRI_BACK_BOT_API_KEY``.
BOT_API_KEY = (env_lookup("TRI_BACK_BOT_API_KEY") or "").strip()
TRAVERSAL_MODE = _env_str("TRAVERSAL_MODE", "bot")
IDLE_TIMEOUT_SEC = _env_int("IDLE_TIMEOUT_SEC", 60)
MAX_STORED_MESSAGES = 40
LOGIN_RATE_LIMIT = 8
LOGIN_RATE_WINDOW_SEC = 300

# Study-only welcome (not sent to the bot intake pipeline).
# Default copy must match bot ``app.triage_profiles.LOW_BACK_INTRO_MESSAGE``.
INTRO_MESSAGE_ID = "msg_intro"
INTRO_DELAY_SEC = _env_int("TRI_BACK_INTRO_DELAY_SEC", 5)
INTRO_MESSAGE = _env_str(
    "TRI_BACK_INTRO_MESSAGE",
    "Hi, I'm TRI-BACK. I'm designed to help rule out any concerning patterns "
    "with your low back pain. This is not a medical diagnosis. If you "
    "think you have an emergency, seek urgent care right away. When you're ready, "
    "let's start with your age and the sex you were assigned at birth.",
)

PUBLIC_ACCESS = _env_bool("TRI_BACK_PUBLIC_ACCESS", False)
# Optional metadata only. Hosted WebSockets use the page origin, not this value.
PUBLIC_BASE_URL = _env_str("TRI_BACK_PUBLIC_BASE_URL", "").rstrip("/")
# 7 days local; 12 hours when public HTTPS share link is active.
SESSION_COOKIE_MAX_AGE = 12 * 60 * 60 if PUBLIC_ACCESS else 7 * 24 * 60 * 60

# Hosted study UI must send the same Bearer key the bot requires.
if PUBLIC_ACCESS and not BOT_API_KEY:
    raise RuntimeError(
        "TRI_BACK_PUBLIC_ACCESS=1 requires TRI_BACK_BOT_API_KEY "
        "(study UI must authenticate to the bot API)."
    )
