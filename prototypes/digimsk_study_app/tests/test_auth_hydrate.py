"""Auth hydration from session snapshots."""

from __future__ import annotations

from pathlib import Path

import pytest

from digimsk_study_app.auth.hydrate import auth_fields_from_session
from digimsk_study_app.session_store import init_session


@pytest.fixture()
def sessions_dir(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("digimsk_study_app.session_store.SESSIONS_DIR", tmp_path)
    monkeypatch.setattr("digimsk_study_app.config.SESSIONS_DIR", tmp_path)
    return tmp_path


def test_auth_fields_from_session(sessions_dir):
    init_session(
        "admin_1",
        study_id="admin",
        role="admin",
        group_id=3,
        login_count=1,
        login_at="2026-07-03T18:00:00-07:00",
    )
    fields = auth_fields_from_session("admin_1")
    assert fields is not None
    assert fields["is_authenticated"] is True
    assert fields["study_id"] == "admin"
    assert fields["role"] == "admin"
    assert fields["group_id"] == 3
    assert fields["session_id"] == "admin_1"


def test_auth_fields_missing_session(sessions_dir):
    assert auth_fields_from_session("") is None
    assert auth_fields_from_session("missing_1") is None
