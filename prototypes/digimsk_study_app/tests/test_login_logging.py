"""Login logging tests."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from digimsk_study_app.auth.passwords import hash_password
from digimsk_study_app.auth.session import login_participant
from digimsk_study_app.config import STUDY_DB_PATH
from digimsk_study_app.db import login_events as login_db
from digimsk_study_app.db import users as users_db
from digimsk_study_app.db.connection import init_schema


@pytest.fixture()
def temp_db(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test.db"
        monkeypatch.setattr("digimsk_study_app.config.STUDY_DB_PATH", db_path)
        init_schema()
        users_db.insert_user("425", hash_password("secretpass12"), 2)
        yield db_path


def test_login_records_event_and_increments_count(temp_db):
    result = login_participant("425", "secretpass12")
    assert result.ok
    assert result.session_id == "425_1"
    assert result.login_count == 1
    user = users_db.get_user_by_study_id("425")
    assert user["login_count"] == 1
    events = login_db.list_login_events()
    assert len(events) == 1
    assert events[0]["study_id"] == "425"
    assert events[0]["session_id"] == "425_1"
    assert events[0]["group_id"] == 2

    result2 = login_participant("425", "secretpass12")
    assert result2.session_id == "425_2"
    assert result2.login_count == 2
