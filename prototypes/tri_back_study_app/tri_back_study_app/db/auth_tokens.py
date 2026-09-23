"""Server-side login tokens. The cookie holds a token, never a session file id."""

from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Any

from tri_back_study_app.db.connection import db_connection


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def create_token(*, study_id: str, role: str, session_file_id: str) -> str:
    token = secrets.token_urlsafe(32)
    with db_connection() as conn:
        conn.execute(
            """
            INSERT INTO auth_tokens (token, study_id, role, session_file_id, revoked, created_at)
            VALUES (?, ?, ?, ?, 0, ?)
            """,
            (token, study_id, role, session_file_id, _now_iso()),
        )
    return token


def get_valid_token(token: str) -> dict[str, Any] | None:
    raw = (token or "").strip()
    if not raw:
        return None
    with db_connection() as conn:
        row = conn.execute(
            """
            SELECT token, study_id, role, session_file_id, revoked, created_at
            FROM auth_tokens
            WHERE token = ? AND revoked = 0
            """,
            (raw,),
        ).fetchone()
    return dict(row) if row else None


def revoke_token(token: str) -> None:
    raw = (token or "").strip()
    if not raw:
        return
    with db_connection() as conn:
        conn.execute(
            "UPDATE auth_tokens SET revoked = 1 WHERE token = ?",
            (raw,),
        )
