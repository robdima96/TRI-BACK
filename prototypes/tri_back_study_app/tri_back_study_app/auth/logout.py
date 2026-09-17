"""Logout arm/confirm and session-file stamp (no new dump path)."""

from __future__ import annotations

from pathlib import Path

from tri_back_study_app.session_store import load_session, save_session, session_file_path

LOGOUT_LABEL = "Logout"
LOGOUT_CONFIRM_LABEL = "Are you sure you want to log out?"
LOGOUT_CONFIRM_TIMEOUT_SEC = 5.0


def should_complete_logout(confirming: bool) -> bool:
    """True on the second click (already armed)."""
    return bool(confirming)


def should_disarm_logout(confirming: bool, current_arm_id: int, started_arm_id: int) -> bool:
    """True when the confirm timeout should restore the idle Logout button."""
    return bool(confirming) and current_arm_id == started_arm_id


def stamp_session_json(session_id: str) -> Path | None:
    """Stamp ``last_active_at`` on the existing study session file.

    Same ``{SESSIONS_DIR}/{sid}.json`` as ``init_session``. Does not create a
    second copy. Returns the path when a file was written, else ``None``.
    """
    sid = (session_id or "").strip()
    if not sid:
        return None
    session = load_session(sid)
    if not session:
        return None
    path = session_file_path(sid)
    save_session(sid, **session)
    return path
