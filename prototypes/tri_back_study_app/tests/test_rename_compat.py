"""Cookie name and local admin fallback after the TRI-BACK rebrand."""

from __future__ import annotations

import inspect

import pytest

from tri_back_study_app.auth.passwords import verify_admin_password
from tri_back_study_app.state.auth_state import AuthState


def test_session_cookie_is_tri_back_sid():
    src = inspect.getsource(AuthState)
    assert 'name="tri_back_sid"' in src


def test_logout_does_not_set_undeclared_legacy_sid():
    """Reflex raises SetUndefinedStateVarError if logout assigns _legacy_sid."""
    src = inspect.getsource(AuthState)
    assert "_legacy_sid" not in src
    assert "logout_confirming" in src
    assert "request_logout" in src


def test_chat_and_admin_share_logout_button():
    from tri_back_study_app.pages import admin as admin_page
    from tri_back_study_app.pages import chat as chat_page

    assert "logout_button" in inspect.getsource(chat_page)
    assert "logout_button" in inspect.getsource(admin_page)
    from tri_back_study_app.components.logout_button import logout_button as btn

    src = inspect.getsource(btn)
    assert "request_logout" in src
    assert "btn-logout-confirm" in src


def test_local_admin_accepts_triback(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("tri_back_study_app.config.PUBLIC_ACCESS", False)
    monkeypatch.delenv("TRI_BACK_ADMIN_PASSWORD", raising=False)
    assert verify_admin_password("triback") is True
    assert verify_admin_password("wrong") is False
