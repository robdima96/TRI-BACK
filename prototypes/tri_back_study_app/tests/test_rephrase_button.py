"""Rephrase control sits beside thumbs and is one-shot."""

from __future__ import annotations

import inspect

from tri_back_study_app.components import feedback_row as feedback_mod
from tri_back_study_app.models.chat_types import empty_message
from tri_back_study_app.state.chat_state import ChatState, _messages_to_session


def test_feedback_row_includes_rephrase_control():
    src = inspect.getsource(feedback_mod.feedback_row)
    assert "rephrase this" in src
    assert "ChatState.rate_message" in src
    assert "ChatState.rephrase_message" in src


def test_empty_message_defaults_rephrase_flags():
    msg = empty_message(message_id="msg_000", role="assistant", content="How old are you?", timestamp="")
    assert msg["question_mode"] is False
    assert msg["rephrased"] is False


def test_messages_to_session_persist_rephrased():
    msg = empty_message(
        message_id="msg_000",
        role="assistant",
        content="How old are you?",
        timestamp="2026-09-20T00:00:00+00:00",
        question_mode=True,
        rephrased=True,
    )
    rows = _messages_to_session([msg])
    assert rows[0]["question_mode"] is True
    assert rows[0]["rephrased"] is True


def test_chat_state_has_rephrase_handler():
    assert hasattr(ChatState, "rephrase_message")
