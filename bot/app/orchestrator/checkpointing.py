"""SQLite-backed LangGraph checkpointer (thread_id = session_id)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver

from app.config import settings

_conn: sqlite3.Connection | None = None
_saver: SqliteSaver | None = None


def get_checkpointer() -> SqliteSaver:
    global _conn, _saver
    if _saver is None:
        path = Path(settings.checkpoint_sqlite_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        _conn = sqlite3.connect(str(path.resolve()), check_same_thread=False)
        _saver = SqliteSaver(_conn)
    return _saver


def close_checkpointer() -> None:
    global _conn, _saver
    if _conn is not None:
        try:
            _conn.close()
        except sqlite3.Error:
            pass
        _conn = None
    _saver = None
