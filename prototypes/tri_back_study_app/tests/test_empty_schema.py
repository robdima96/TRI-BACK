"""First start creates an empty study database and does not seed users."""

from __future__ import annotations

from tri_back_study_app.db.connection import init_schema
from tri_back_study_app.db import users as users_db


def test_init_schema_creates_empty_users(tmp_path, monkeypatch):
    db_path = tmp_path / "tri_back.db"
    monkeypatch.setattr("tri_back_study_app.config.STUDY_DB_PATH", db_path)
    init_schema()
    assert db_path.is_file()
    assert users_db.list_users() == []


def test_run_local_does_not_seed():
    from pathlib import Path
    import importlib.util

    run_local = Path(__file__).resolve().parents[1] / "scripts" / "run_local.py"
    text = run_local.read_text(encoding="utf-8")
    assert "seed_users" not in text
    assert "generate_roster" not in text
    spec = importlib.util.spec_from_file_location("tri-back_run_local", run_local)
    assert spec is not None
