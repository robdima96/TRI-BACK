"""Load conversational vignette scenarios from CSV."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

TURN_COLUMNS = ("q1", "q2", "q3", "q4", "q5")


@dataclass(frozen=True)
class Scenario:
    source: str
    full_query: str
    ada_disposition: str
    patient_turns: tuple[str, str, str, str, str]


def load_scenarios(
    csv_path: Path,
    *,
    sources: list[str] | None = None,
) -> list[Scenario]:
    with csv_path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))

    scenarios: list[Scenario] = []
    for row in rows:
        source = (row.get("source") or "").strip()
        if not source:
            continue
        if sources and source not in sources:
            continue

        turns = tuple((row.get(col) or "").strip() for col in TURN_COLUMNS)
        if any(not t for t in turns):
            raise ValueError(f"Scenario {source!r} is missing one or more q1–q5 values.")

        scenarios.append(
            Scenario(
                source=source,
                full_query=(row.get("query") or "").strip(),
                ada_disposition=(row.get("Ada_disposition") or "").strip(),
                patient_turns=turns,  # type: ignore[arg-type]
            )
        )

    return scenarios
