"""Session store and feedback persistence tests."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from tri_back_study_app.session_store import init_session, load_session, save_session


@pytest.fixture()
def sessions_dir(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp)
        monkeypatch.setattr("tri_back_study_app.session_store.SESSIONS_DIR", path)
        monkeypatch.setattr("tri_back_study_app.config.SESSIONS_DIR", path)
        yield path


def test_session_atomic_write_and_feedback(sessions_dir):
    init_session(
        "425_1",
        study_id="425",
        role="participant",
        group_id=2,
        login_count=1,
        login_at="2026-07-03T13:45:00-07:00",
    )
    data = load_session("425_1")
    assert data is not None
    assert data["study_id"] == "425"
    messages = [
        {
            "message_id": "msg_000",
            "role": "assistant",
            "content": "Hello",
            "feedback": {"rating": "up", "rated_at": "2026-07-03T13:46:45-07:00"},
        }
    ]
    save_session("425_1", messages=messages, engagement={"feedback_up_count": 1, "feedback_down_count": 0})
    reloaded = load_session("425_1")
    assert reloaded["messages"][0]["feedback"]["rating"] == "up"
    files = list(sessions_dir.glob("425_1.json"))
    assert len(files) == 1
    payload = json.loads(files[0].read_text(encoding="utf-8"))
    assert payload["session_id"] == "425_1"


def test_save_session_retries_stale_loads_before_refusing(sessions_dir, monkeypatch):
    path = sessions_dir / "admin_8.json"
    path.write_text('{"session_id": "admin_8", "keep": true}', encoding="utf-8")
    attempts = {"n": 0}

    def flaky_load(_sid):
        attempts["n"] += 1
        if attempts["n"] < 3:
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    monkeypatch.setattr("tri_back_study_app.session_store.load_session", flaky_load)
    save_session("admin_8", messages=[{"role": "assistant", "content": "hi"}])
    assert attempts["n"] >= 3
    reloaded = json.loads(path.read_text(encoding="utf-8"))
    assert reloaded["keep"] is True
    assert reloaded["messages"][0]["content"] == "hi"


def test_save_session_refuses_to_clobber_unreadable_file(sessions_dir, monkeypatch):
    path = sessions_dir / "admin_7.json"
    path.write_text('{"session_id": "admin_7", "keep": true}', encoding="utf-8")
    monkeypatch.setattr("tri_back_study_app.session_store.load_session", lambda _sid: None)
    with pytest.raises(OSError, match="refusing to overwrite"):
        save_session("admin_7", messages=[])
    assert json.loads(path.read_text(encoding="utf-8"))["keep"] is True


def test_save_session_accepts_full_loaded_dict_unpack(sessions_dir):
    """Logout path: save_session(sid, **load_session(sid)) must not TypeError."""
    init_session(
        "admin_1",
        study_id="admin",
        role="admin",
        group_id=2,
        login_count=1,
        login_at="2026-07-22T12:00:00-07:00",
    )
    session = load_session("admin_1")
    assert session is not None
    assert "session_id" in session
    save_session("admin_1", **session)
    reloaded = load_session("admin_1")
    assert reloaded is not None
    assert reloaded["session_id"] == "admin_1"
    assert reloaded["study_id"] == "admin"