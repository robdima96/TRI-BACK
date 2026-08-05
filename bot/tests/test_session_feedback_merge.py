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
