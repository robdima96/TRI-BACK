"""Restore auth fields from a server-side token, then the session file."""

from __future__ import annotations

from typing import Any

from tri_back_study_app.db.auth_tokens import get_valid_token
from tri_back_study_app.session_store import load_session


def auth_fields_from_token(token: str) -> dict[str, Any] | None:
    """Resolve a cookie token to study fields. Never treats the token as a file id."""
    row = get_valid_token(token)
    if not row:
        return None
    file_id = str(row["session_file_id"] or "").strip()
    if not file_id:
        return None
    data = load_session(file_id) or {}
    return {
        "is_authenticated": True,
        "study_id": str(data.get("study_id") or row["study_id"] or ""),
        "role": str(data.get("role") or row["role"] or ""),
        "group_id": int(data.get("group_id") or 1),
        "session_id": file_id,
        "login_count": int(data.get("login_count") or 0),
        "login_at": str(data.get("login_at") or ""),
    }


def auth_fields_from_session(session_file_id: str) -> dict[str, Any] | None:
    """Load auth-related fields from a known session file id (not a cookie)."""
    sid = (session_file_id or "").strip()
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
