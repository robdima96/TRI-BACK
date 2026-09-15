"""SQLite connection helpers."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path

def get_db_path() -> Path:
    from tri_back_study_app import config

    return config.STUDY_DB_PATH


@contextmanager
def db_connection(*, row_factory: bool = True):
    path = get_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    if row_factory:
        conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_schema(schema_path: Path | None = None) -> None:
    root = Path(__file__).resolve().parent
    sql_path = schema_path or (root / "schema.sql")
    sql = sql_path.read_text(encoding="utf-8")
    with db_connection() as conn:
        conn.executescript(sql)
