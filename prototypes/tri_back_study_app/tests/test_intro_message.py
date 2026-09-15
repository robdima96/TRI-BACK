"""Intro choreography helpers (study-only welcome message)."""

from __future__ import annotations

from tri_back_study_app.config import INTRO_DELAY_SEC, INTRO_MESSAGE, INTRO_MESSAGE_ID
from tri_back_study_app.state.chat_state import build_intro_message, should_play_intro


def test_intro_constants():
    assert INTRO_MESSAGE_ID == "msg_intro"
    assert INTRO_DELAY_SEC == 10
    assert "TRI-BACK" in INTRO_MESSAGE


def test_should_play_intro_only_when_empty():
    assert should_play_intro([]) is True
    assert should_play_intro([{"message_id": INTRO_MESSAGE_ID}]) is False


def test_build_intro_message_is_study_local():
    msg = build_intro_message(timestamp="2026-08-05T12:00:00+00:00")
    assert msg["message_id"] == INTRO_MESSAGE_ID
    assert msg["role"] == "assistant"
    assert msg["content"] == INTRO_MESSAGE
    assert msg["feedback_rating"] == ""
    assert msg["has_graph"] is False
    assert msg["reasoning_text"] == ""
