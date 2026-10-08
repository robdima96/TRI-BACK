"""Bot session_store feedback merge across study overlays."""

from __future__ import annotations

import json
from pathlib import Path

from app.session_store import load_session, save_session


def test_bot_save_preserves_study_feedback(tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.settings.session_store_dir", tmp_path)
    monkeypatch.setattr("app.session_store.settings.session_store_dir", tmp_path)

    sid = "admin_9"
    path = tmp_path / f"{sid}.json"
    path.write_text(
        json.dumps(
            {
                "session_id": sid,
                "messages": [
                    {"role": "user", "content": "hello", "message_id": "msg_000"},
                    {
                        "role": "assistant",
                        "content": "How old are you?",
                        "message_id": "msg_001",
                        "feedback": {
                            "rating": "up",
                            "rated_at": "2026-08-05T12:01:00+00:00",
                        },
                    },
                ],
                "engagement": {
                    "turns": [],
                    "feedback_up_count": 1,
                    "feedback_down_count": 0,
                    "session_duration_sec": 12.5,
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    save_session(
        sid,
        messages=[
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "How old are you?"},
            {"role": "user", "content": "50"},
            {"role": "assistant", "content": "What sex?"},
        ],
    )
    data = load_session(sid)
    assert data is not None
    assert data["messages"][1]["feedback"]["rating"] == "up"
    assert data["messages"][1]["message_id"] == "msg_001"
    assert data["engagement"]["feedback_up_count"] == 1
    assert data["engagement"]["session_duration_sec"] == 12.5


def test_save_session_retries_stale_write(tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.settings.session_store_dir", tmp_path)
    monkeypatch.setattr("app.session_store.settings.session_store_dir", tmp_path)
    real_write = Path.write_text
    calls = {"n": 0}

    def flaky(self, data, encoding=None, errors=None, newline=None):
        if self.suffix == ".tmp":
            calls["n"] += 1
            if calls["n"] == 1:
                err = OSError(116, "Stale file handle")
                raise err
        return real_write(self, data, encoding=encoding, errors=errors, newline=newline)

    monkeypatch.setattr(Path, "write_text", flaky)
    save_session("admin_3", messages=[{"role": "user", "content": "hi"}])
    assert calls["n"] >= 2
    loaded = load_session("admin_3")
    assert loaded is not None
    assert loaded["messages"][0]["content"] == "hi"


def test_save_session_refuses_to_clobber_unreadable_file(tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.settings.session_store_dir", tmp_path)
    monkeypatch.setattr("app.session_store.settings.session_store_dir", tmp_path)
    path = tmp_path / "admin_7.json"
    path.write_text('{"session_id": "admin_7", "keep": true}', encoding="utf-8")
    monkeypatch.setattr("app.session_store.load_session", lambda _sid: None)
    try:
        save_session("admin_7", messages=[{"role": "user", "content": "x"}])
        raised = False
    except OSError as exc:
        raised = True
        assert "refusing to overwrite" in str(exc)
    assert raised
    assert json.loads(path.read_text(encoding="utf-8"))["keep"] is True
