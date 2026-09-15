"""Cookie rename + local admin fallbacks after DigiMSK → TRI-BACK."""

from __future__ import annotations

import inspect

import pytest

from tri_back_study_app.auth.passwords import verify_admin_password
from tri_back_study_app.state.auth_state import AuthState


def test_session_cookie_is_tri_back_sid_with_legacy_copy():
    src = inspect.getsource(AuthState)
    assert 'name="tri_back_sid"' in src
    assert 'name="digimsk_sid"' in src
    assert "self.session_id = self._legacy_sid" in src


def test_local_admin_accepts_triback_and_legacy_digimsk(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("tri_back_study_app.config.PUBLIC_ACCESS", False)
    monkeypatch.delenv("TRI_BACK_ADMIN_PASSWORD", raising=False)
    monkeypatch.delenv("DIGIMSK_ADMIN_PASSWORD", raising=False)
    assert verify_admin_password("triback") is True
    assert verify_admin_password("digimsk") is True
    assert verify_admin_password("wrong") is False
