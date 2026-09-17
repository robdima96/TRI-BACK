"""Intro choreography helpers (study-only welcome message)."""

from __future__ import annotations

import inspect

from tri_back_study_app.config import INTRO_DELAY_SEC, INTRO_MESSAGE, INTRO_MESSAGE_ID
from tri_back_study_app.state.chat_state import (
    build_intro_message,
    intro_mount_action,
    should_play_intro,
)


def test_intro_constants():
    assert INTRO_MESSAGE_ID == "msg_intro"
    assert INTRO_DELAY_SEC == 5
    assert "TRI-BACK" in INTRO_MESSAGE
    assert "low back pain" in INTRO_MESSAGE.casefold()
    assert "concerning patterns" in INTRO_MESSAGE


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


def test_intro_mount_action_retries_when_auth_not_ready():
    assert intro_mount_action(authenticated=False, messages=[]) == "retry"
    assert intro_mount_action(authenticated=False, messages=[], after_retry=True) == "redirect"


def test_intro_mount_action_plays_when_empty_and_authed():
    assert intro_mount_action(authenticated=True, messages=[]) == "play"


def test_intro_mount_action_skips_existing_transcript():
    assert (
        intro_mount_action(
            authenticated=True,
            messages=[{"message_id": INTRO_MESSAGE_ID}],
        )
        == "skip"
    )


def test_chat_page_does_not_use_on_mount_for_intro():
    from tri_back_study_app.pages import chat as chat_page

    src = inspect.getsource(chat_page)
    assert "on_mount" not in src
    assert "mount_chat" not in src


def test_app_loads_intro_on_chat_page():
    from tri_back_study_app import tri_back_study_app as app_mod

    src = inspect.getsource(app_mod)
    assert "on_load=ChatState.mount_chat" in src


def test_login_handlers_start_intro():
    from tri_back_study_app.state.auth_state import AuthState

    src = inspect.getsource(AuthState)
    assert src.count("ChatState.mount_chat") == 2
