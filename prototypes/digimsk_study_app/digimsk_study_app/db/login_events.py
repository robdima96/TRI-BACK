"""Login event persistence."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from digimsk_study_app.db.connection import db_connection


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def record_login_event(
    *,
    study_id: str,
    role: str,
    session_id: str,
    group_id: int | None,
    login_at: str | None = None,
) -> None:
    with db_connection() as conn:
        conn.execute(
            """
            INSERT INTO login_events (study_id, role, login_at, session_id, group_id)
            VALUES (?, ?, ?, ?, ?)
            """,
            (study_id, role, login_at or _now_iso(), session_id, group_id),
        )


def list_login_events(limit: int = 500) -> list[dict[str, Any]]:
    with db_connection() as conn:
        rows = conn.execute(
            """
            SELECT * FROM login_events
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_admin_meta() -> dict[str, Any]:
    with db_connection() as conn:
        row = conn.execute("SELECT * FROM admin_meta WHERE id = 1").fetchone()
        return dict(row) if row else {"login_count": 0}


def increment_admin_login() -> dict[str, Any]:
    now = _now_iso()
    with db_connection() as conn:
        row = conn.execute("SELECT * FROM admin_meta WHERE id = 1").fetchone()
        if not row:
            conn.execute(
                "INSERT INTO admin_meta (id, login_count, first_login_at, last_login_at) VALUES (1, 1, ?, ?)",
                (now, now),
            )
        else:
            login_count = int(row["login_count"]) + 1
            first = row["first_login_at"] or now
            conn.execute(
                """
                UPDATE admin_meta
                SET login_count = ?, first_login_at = ?, last_login_at = ?
                WHERE id = 1
                """,
                (login_count, first, now),
            )
        updated = conn.execute("SELECT * FROM admin_meta WHERE id = 1").fetchone()
        return dict(updated)


def record_admin_action(action: str, target_study_id: str | None = None, detail: str | None = None) -> None:
    with db_connection() as conn:
        conn.execute(
            """
            INSERT INTO admin_actions (action, target_study_id, detail, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (action, target_study_id, detail, _now_iso()),
        )
