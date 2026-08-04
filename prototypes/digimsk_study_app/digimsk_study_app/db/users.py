"""Participant user CRUD."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from digimsk_study_app.db.connection import db_connection


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def get_user_by_study_id(study_id: str) -> dict[str, Any] | None:
    with db_connection() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE study_id = ?",
            (study_id,),
        ).fetchone()
        return dict(row) if row else None


def list_users() -> list[dict[str, Any]]:
    with db_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM users ORDER BY study_id"
        ).fetchall()
        return [dict(r) for r in rows]


def insert_user(study_id: str, password_hash: str, group_id: int) -> None:
    with db_connection() as conn:
        conn.execute(
            """
            INSERT INTO users (study_id, password_hash, group_id)
            VALUES (?, ?, ?)
            """,
            (study_id, password_hash, group_id),
        )


def increment_login(study_id: str) -> dict[str, Any]:
    now = _now_iso()
    with db_connection() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE study_id = ?",
            (study_id,),
        ).fetchone()
        if not row:
            raise KeyError(study_id)
        login_count = int(row["login_count"]) + 1
        first = row["first_login_at"] or now
        conn.execute(
            """
            UPDATE users
            SET login_count = ?, first_login_at = ?, last_login_at = ?
            WHERE study_id = ?
            """,
            (login_count, first, now, study_id),
        )
        updated = conn.execute(
            "SELECT * FROM users WHERE study_id = ?",
            (study_id,),
        ).fetchone()
        return dict(updated)


def group_counts() -> dict[int, int]:
    with db_connection() as conn:
        rows = conn.execute(
            "SELECT group_id, COUNT(*) AS n FROM users GROUP BY group_id"
        ).fetchall()
        return {int(r["group_id"]): int(r["n"]) for r in rows}
