#!/usr/bin/env python3
"""Initialize SQLite schema for the study app."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from digimsk_study_app.db.connection import init_schema


def main() -> int:
    init_schema()
    print("Database initialized.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
