"""Rephrase control sits beside thumbs and is one-shot."""

from __future__ import annotations

import asyncio
import inspect
from unittest.mock import AsyncMock, MagicMock, patch

from tri_back_study_app.adapters.http_client import call_rephrase_api
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


def test_rephrase_http_error_is_api_detail_without_url():
    resp = MagicMock()
    resp.status_code = 404
    resp.json = MagicMock(return_value={"detail": "message not found"})
    client = AsyncMock()
    client.post = AsyncMock(return_value=resp)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)

    message = ""
    with patch(
        "tri_back_study_app.adapters.http_client.httpx.AsyncClient",
        return_value=client,
    ):
        try:
            asyncio.run(call_rephrase_api("admin_1", "msg_000"))
        except RuntimeError as exc:
            message = str(exc)
        else:
            raise AssertionError("rephrase HTTP error was not raised")
    banner = f"Could not rephrase that question: {message}"
    assert message == "message not found"
    assert "http" not in banner.casefold()
