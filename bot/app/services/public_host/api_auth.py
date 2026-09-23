"""Bot chat API Bearer auth and simple in-memory rate limits."""

from __future__ import annotations

import secrets
import time
from collections import defaultdict, deque

from fastapi import Header, HTTPException, Request

from app.config import settings


def require_bot_api_key(
    authorization: str | None = Header(default=None),
) -> None:
    """Require a matching Bearer key unless ``TRI_BACK_ALLOW_OPEN_API=1``."""
    expected = (settings.bot_api_key or "").strip()
    if not expected:
        if settings.allow_open_api:
            return
        raise HTTPException(status_code=401, detail="Bearer token required")
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Bearer token required")
    token = authorization[7:].strip()
    if not token or not secrets.compare_digest(token, expected):
        raise HTTPException(status_code=401, detail="Invalid API key")


_session_hits: dict[str, deque[float]] = defaultdict(deque)
_ip_hits: dict[str, deque[float]] = defaultdict(deque)


def _prune(window: deque[float], now: float, window_sec: float) -> None:
    while window and window[0] < now - window_sec:
        window.popleft()


def enforce_chat_rate_limit(request: Request, session_id: str) -> None:
    """Per-session and per-IP sliding windows for ``POST /api/v1/chat``."""
    limit = int(settings.chat_rate_limit)
    window_sec = float(settings.chat_rate_window_sec)
    if limit <= 0 or window_sec <= 0:
        return

    now = time.monotonic()
    sid = (session_id or "").strip() or "_empty"
    client = request.client.host if request.client else "unknown"

    sess_q = _session_hits[sid]
    _prune(sess_q, now, window_sec)
    if len(sess_q) >= limit:
        raise HTTPException(status_code=429, detail="Rate limit exceeded for session")
    sess_q.append(now)

    ip_q = _ip_hits[client]
    _prune(ip_q, now, window_sec)
    # Slightly looser IP bucket (3x session) so multi-tab admin is not blocked.
    if len(ip_q) >= limit * 3:
        raise HTTPException(status_code=429, detail="Rate limit exceeded for client")
    ip_q.append(now)
