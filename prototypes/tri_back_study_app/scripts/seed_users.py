#!/usr/bin/env python3
"""Seed 90 participant accounts from a roster CSV."""

from __future__ import annotations

import argparse
import csv
import secrets
import string
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tri_back_study_app.auth.passwords import hash_password
from tri_back_study_app.db.connection import init_schema
from tri_back_study_app.db.users import get_user_by_study_id, insert_user


def _random_password(length: int = 14) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _read_roster(path: Path) -> list[tuple[str, int]]:
    rows: list[tuple[str, int]] = []
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            study_id = (row.get("study_id") or "").strip()
            group_id = int(row.get("group_id") or 0)
            if study_id and group_id in (1, 2, 3):
                rows.append((study_id, group_id))
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed participant accounts")
    parser.add_argument("--roster", required=True, help="CSV with study_id,group_id")
    parser.add_argument(
        "--credentials-out",
        default=str(ROOT / "data" / "participant_credentials.csv"),
        help="One-time plaintext credentials output",
    )
    args = parser.parse_args()
    roster_path = Path(args.roster)
    if not roster_path.is_file():
        print(f"Roster not found: {roster_path}", file=sys.stderr)
        return 1

    init_schema()
    roster = _read_roster(roster_path)
    if len(roster) != 90:
        print(f"Warning: expected 90 roster rows, got {len(roster)}")

    cred_path = Path(args.credentials_out)
    cred_path.parent.mkdir(parents=True, exist_ok=True)
    created = 0
    with cred_path.open("w", encoding="utf-8", newline="") as out:
        writer = csv.writer(out)
        writer.writerow(["study_id", "password", "group_id"])
        for study_id, group_id in roster:
            if get_user_by_study_id(study_id):
                continue
            password = _random_password()
            insert_user(study_id, hash_password(password), group_id)
            writer.writerow([study_id, password, group_id])
            created += 1

    print(f"Seeded {created} users; credentials written to {cred_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
