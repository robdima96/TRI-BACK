"""Two-click logout helpers and same-path session stamp."""

from __future__ import annotations

from pathlib import Path

import pytest

from tri_back_study_app.auth.hydrate import auth_fields_from_session
from tri_back_study_app.auth.logout import (
    LOGOUT_CONFIRM_LABEL,
    LOGOUT_CONFIRM_TIMEOUT_SEC,
    should_complete_logout,
    should_disarm_logout,
    stamp_session_json,
)
from tri_back_study_app.session_store import (
    init_session,
    load_session,
    session_file_path,
)
from tri_back_study_app.state.chat_state import chat_view_from_session


@pytest.fixture()
def sessions_dir(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("tri_back_study_app.session_store.SESSIONS_DIR", tmp_path)
    monkeypatch.setattr("tri_back_study_app.config.SESSIONS_DIR", tmp_path)
    return tmp_path


def test_first_click_arms_second_click_completes():
    assert should_complete_logout(False) is False
    assert should_complete_logout(True) is True
    assert "log out" in LOGOUT_CONFIRM_LABEL.casefold()


def test_confirm_timeout_disarms_only_matching_arm():
    assert LOGOUT_CONFIRM_TIMEOUT_SEC == 5.0
    assert should_disarm_logout(True, 1, 1) is True
    assert should_disarm_logout(False, 1, 1) is False
    assert should_disarm_logout(True, 2, 1) is False


def test_logout_stamp_uses_init_session_path(sessions_dir: Path):
    init_session(
        "admin_1",
        study_id="admin",
        role="admin",
        group_id=1,
        login_count=1,
        login_at="2026-09-15T18:00:00-07:00",
    )
    expected = sessions_dir / "admin_1.json"
    assert session_file_path("admin_1") == expected
    names_before = {p.name for p in sessions_dir.glob("*.json")}
    assert load_session("admin_1") is not None
    stamped = stamp_session_json("admin_1")
    assert stamped == expected
    names_after = {p.name for p in sessions_dir.glob("*.json")}
    assert names_after == names_before
    after = load_session("admin_1")
    assert after is not None
    assert after["session_id"] == "admin_1"
    assert after["study_id"] == "admin"
    assert after["last_active_at"]


def test_stamp_missing_or_empty_sid_is_noop(sessions_dir: Path):
    assert stamp_session_json("") is None
    assert stamp_session_json("missing_1") is None
    assert list(sessions_dir.glob("*.json")) == []


def test_empty_sid_does_not_hydrate():
    assert auth_fields_from_session("") is None


def test_missing_session_wipes_chat_view():
    fields = chat_view_from_session(None)
    assert fields["messages"] == []
    assert fields["turn_count"] == 0
    assert fields["escalated"] is False
    assert fields["safety_reason"] == ""


def test_loaded_session_maps_chat_view():
    fields = chat_view_from_session(
        {
            "messages": [{"role": "assistant", "content": "Hi", "message_id": "msg_intro"}],
            "turn_count": 2,
            "escalated": True,
            "safety_reason": "urgent",
        }
    )
    assert len(fields["messages"]) == 1
    assert fields["messages"][0]["content"] == "Hi"
    assert fields["turn_count"] == 2
    assert fields["escalated"] is True
    assert fields["safety_reason"] == "urgent"
