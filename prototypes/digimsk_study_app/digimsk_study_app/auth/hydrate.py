"""Restore auth fields from a persisted session snapshot."""

from __future__ import annotations

from typing import Any

from digimsk_study_app.session_store import load_session


def auth_fields_from_session(session_id: str) -> dict[str, Any] | None:
    """Load auth-related fields from the on-disk session file."""
    sid = (session_id or "").strip()
    if not sid:
        return None
    data = load_session(sid)
    if not data:
        return None
    return {
        "is_authenticated": True,
        "study_id": str(data.get("study_id") or ""),
        "role": str(data.get("role") or ""),
        "group_id": int(data.get("group_id") or 1),
        "session_id": sid,
        "login_count": int(data.get("login_count") or 0),
        "login_at": str(data.get("login_at") or ""),
    }
