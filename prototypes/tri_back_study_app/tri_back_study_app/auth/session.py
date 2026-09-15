"""Login orchestration for participants and admin."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from tri_back_study_app.auth.config import ADMIN_STUDY_ID, ADMIN_USERNAME
from tri_back_study_app.auth.passwords import verify_admin_password, verify_password
from tri_back_study_app.auth.session_ids import allocate_session_id
from tri_back_study_app.db import login_events as login_db
from tri_back_study_app.db import users as users_db


@dataclass(frozen=True)
class LoginResult:
    ok: bool
    error: str | None = None
    study_id: str | None = None
    role: str | None = None
    group_id: int | None = None
    session_id: str | None = None
    login_count: int | None = None
    login_at: str | None = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def login_participant(study_id: str, password: str) -> LoginResult:
    user = users_db.get_user_by_study_id(study_id.strip())
    if not user or not verify_password(password, user["password_hash"]):
        return LoginResult(ok=False, error="Invalid credentials")
    updated = users_db.increment_login(study_id)
    login_count = int(updated["login_count"])
    session_id = allocate_session_id(study_id, "participant", login_count)
    login_at = _now_iso()
    login_db.record_login_event(
        study_id=study_id,
        role="participant",
        session_id=session_id,
        group_id=int(updated["group_id"]),
        login_at=login_at,
    )
    return LoginResult(
        ok=True,
        study_id=study_id,
        role="participant",
        group_id=int(updated["group_id"]),
        session_id=session_id,
        login_count=login_count,
        login_at=login_at,
    )


def login_admin(username: str, password: str, selected_arm: int) -> LoginResult:
    if username.strip() != ADMIN_USERNAME:
        return LoginResult(ok=False, error="Invalid credentials")
    if not verify_admin_password(password):
        return LoginResult(ok=False, error="Invalid credentials")
    if selected_arm not in (1, 2, 3):
        return LoginResult(ok=False, error="Select an arm")
    meta = login_db.increment_admin_login()
    login_count = int(meta["login_count"])
    session_id = allocate_session_id(ADMIN_STUDY_ID, "admin", login_count)
    login_at = _now_iso()
    login_db.record_login_event(
        study_id=ADMIN_STUDY_ID,
        role="admin",
        session_id=session_id,
        group_id=selected_arm,
        login_at=login_at,
    )
    login_db.record_admin_action("admin_login", detail=f"arm={selected_arm}")
    return LoginResult(
        ok=True,
        study_id=ADMIN_STUDY_ID,
        role="admin",
        group_id=selected_arm,
        session_id=session_id,
        login_count=login_count,
        login_at=login_at,
    )
