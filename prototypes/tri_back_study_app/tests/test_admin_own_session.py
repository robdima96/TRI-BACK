"""Admin dashboard may only show the current admin's own session JSON."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from tri_back_study_app.session_store import (
    init_session,
    session_detail_for_current_admin,
    sessions_for_current_admin,
)


@pytest.fixture()
def sessions_dir(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp)
        monkeypatch.setattr("tri_back_study_app.session_store.SESSIONS_DIR", path)
        monkeypatch.setattr("tri_back_study_app.config.SESSIONS_DIR", path)
        yield path


def _write_session(sessions_dir: Path, session_id: str, *, messages: list[dict]) -> None:
    init_session(
        session_id,
        study_id="admin" if session_id.startswith("admin_") else "425",
        role="admin" if session_id.startswith("admin_") else "participant",
        group_id=1,
        login_count=1,
        login_at="2026-09-23T12:00:00-07:00",
    )
    path = sessions_dir / f"{session_id}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["messages"] = messages
    path.write_text(json.dumps(data), encoding="utf-8")


def test_admin_list_and_detail_exclude_other_session_files(sessions_dir: Path):
    _write_session(
        sessions_dir,
        "admin_3",
        messages=[{"role": "user", "content": "own turn"}],
    )
    _write_session(
        sessions_dir,
        "admin_1",
        messages=[{"role": "user", "content": "historical transcript"}],
    )
    _write_session(
        sessions_dir,
        "425_1",
        messages=[{"role": "user", "content": "participant transcript"}],
    )

    visible = sessions_for_current_admin("admin_3")
    assert [s["session_id"] for s in visible] == ["admin_3"]
    assert visible[0]["messages"][0]["content"] == "own turn"

    own = session_detail_for_current_admin("admin_3", "admin_3")
    assert own is not None
    assert own["session_id"] == "admin_3"

    assert session_detail_for_current_admin("admin_3", "admin_1") is None
    assert session_detail_for_current_admin("admin_3", "425_1") is None
    assert session_detail_for_current_admin("", "admin_3") is None
