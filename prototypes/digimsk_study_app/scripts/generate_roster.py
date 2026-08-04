#!/usr/bin/env python3
"""Generate a balanced 90-participant roster (30 per arm)."""

from __future__ import annotations

import csv
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "data" / "study_roster.csv"


def main() -> None:
    rows: list[tuple[str, int]] = []
    for i in range(1, 91):
        group_id = ((i - 1) % 3) + 1
        rows.append((f"STUDY{i:03d}", group_id))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["study_id", "group_id"])
        writer.writerows(rows)
    print(f"Wrote {len(rows)} rows to {OUT}")


if __name__ == "__main__":
    main()
