"""Cookie tokens must not open session files by guessable id."""

from __future__ import annotations

from pathlib import Path

import pytest

from tri_back_study_app.auth.hydrate import auth_fields_from_token
from tri_back_study_app.db.auth_tokens import create_token, get_valid_token, revoke_token
from tri_back_study_app.session_store import init_session


@pytest.fixture()
def isolated(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("tri_back_study_app.config.STUDY_DB_PATH", tmp_path / "tri_back.db")
    monkeypatch.setattr("tri_back_study_app.session_store.SESSIONS_DIR", tmp_path)
    monkeypatch.setattr("tri_back_study_app.config.SESSIONS_DIR", tmp_path)
    return tmp_path


def test_token_resolves_to_file_id(isolated: Path):
    init_session(
        "admin_1",
        study_id="admin",
        role="admin",
        group_id=2,
        login_count=1,
        login_at="2026-09-15T18:00:00-07:00",
    )
    token = create_token(study_id="admin", role="admin", session_file_id="admin_1")
    assert token != "admin_1"
    assert get_valid_token("admin_1") is None
    assert auth_fields_from_token("admin_1") is None
    fields = auth_fields_from_token(token)
    assert fields is not None
    assert fields["session_id"] == "admin_1"
    assert fields["role"] == "admin"


def test_revoked_token_is_invalid(isolated: Path):
    init_session(
        "admin_2",
        study_id="admin",
        role="admin",
        group_id=1,
        login_count=2,
        login_at="2026-09-15T18:00:00-07:00",
    )
    token = create_token(study_id="admin", role="admin", session_file_id="admin_2")
    revoke_token(token)
    assert get_valid_token(token) is None
    assert auth_fields_from_token(token) is None


def test_list_users_omits_password_hash(isolated: Path):
    from tri_back_study_app.auth.passwords import hash_password
    from tri_back_study_app.db import users as users_db

    users_db.insert_user("425", hash_password("secretpass12"), 2)
    rows = users_db.list_users()
    assert rows
    assert "password_hash" not in rows[0]
