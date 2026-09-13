"""Parse red-flags edge and factor-sheet CSV rows (mirrors ``Graphs/graph_builder.py``)."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


class FactorSheetError(ValueError):
    """Factors CSV is missing, duplicated, or out of sync with the inventory."""


_FACTOR_SHEET_COLUMNS = (
    "source_nodes",
    "askable",
    "intent",
    "fallback",
    "synonyms",
)


def _boolish(value: str) -> bool:
    return value.strip().lower() in {"yes", "true", "1"}


def _split_synonyms(raw: str) -> tuple[str, ...]:
    parts = [p.strip() for p in (raw or "").split(";")]
    return tuple(p for p in parts if p)


@dataclass(frozen=True)
class ChunkRow:
    chunk_id: str
    chunk_string: str
    source: str
    loc: str
    parent_id: str
    source_nodes: str
    edges: str
    path_type: str
    path: str
    is_specific: bool
    is_guideline: bool
    evidence: str
    evidence_level: str

    @classmethod
    def from_dict(cls, row: dict[str, str]) -> ChunkRow:
        return cls(
            chunk_id=row["chunk_id"].strip(),
            chunk_string=row["chunk_string"].strip(),
            source=row["source"].strip(),
            loc=row["loc"].strip(),
            parent_id=row["parent_id"].strip(),
            source_nodes=row["source_nodes"].strip(),
            edges=row["edges"].strip(),
            path_type=row["path_type"].strip().lower(),
            path=row["path"].strip(),
            is_specific=_boolish(row.get("is_specific", "")),
            is_guideline=_boolish(row.get("is_guideline", "")),
            evidence=row.get("evidence", "").strip(),
            evidence_level=row.get("evidence_level", "").strip(),
        )


def load_chunks(csv_path: Path) -> list[ChunkRow]:
    with csv_path.open(encoding="utf-8-sig", newline="") as handle:
        return [ChunkRow.from_dict(row) for row in csv.DictReader(handle)]


@dataclass(frozen=True)
class FactorRow:
    """One Factor-node row from the v4+ factors CSV (not the edge table)."""

    source_nodes: str
    askable: bool
    intent: str
    fallback: str
    synonyms: tuple[str, ...]

    @classmethod
    def from_dict(cls, row: dict[str, str]) -> FactorRow:
        askable_raw = (row.get("askable") or "").strip().lower()
        if askable_raw not in {"yes", "no"}:
            raise FactorSheetError(
                f"Factors CSV {row.get('source_nodes')!r}: "
                f"askable must be yes|no, got {askable_raw!r}"
            )
        return cls(
            source_nodes=(row.get("source_nodes") or "").strip(),
            askable=askable_raw == "yes",
            intent=(row.get("intent") or "").strip(),
            fallback=(row.get("fallback") or "").strip(),
            synonyms=_split_synonyms(row.get("synonyms") or ""),
        )


def load_inventory_factors(inventory_path: Path) -> tuple[str, ...]:
    if not inventory_path.is_file():
        raise FactorSheetError(f"Inventory not found: {inventory_path}")
    data = json.loads(inventory_path.read_text(encoding="utf-8"))
    factors = data.get("factors") or []
    return tuple(str(name).strip() for name in factors if str(name).strip())


def _validate_factor_sheet(
    rows: list[FactorRow], inventory_factors: Sequence[str]
) -> None:
    names: list[str] = []
    seen: set[str] = set()
    dupes: list[str] = []
    for row in rows:
        name = row.source_nodes
        if not name:
            raise FactorSheetError("Factors CSV row has empty source_nodes")
        if name in seen:
            dupes.append(name)
        seen.add(name)
        names.append(name)
        if row.askable:
            missing = [
                col
                for col, val in (
                    ("intent", row.intent),
                    ("fallback", row.fallback),
                    ("synonyms", " ".join(row.synonyms)),
                )
                if not val
            ]
            if missing:
                raise FactorSheetError(
                    f"Factors CSV {name!r}: askable=yes requires {', '.join(missing)}"
                )
    if dupes:
        raise FactorSheetError(
            "Factors CSV has duplicate source_nodes: "
            + ", ".join(sorted(set(dupes)))
        )
    inventory_set = set(inventory_factors)
    sheet_set = set(names)
    missing = sorted(inventory_set - sheet_set)
    extra = sorted(sheet_set - inventory_set)
    if missing or extra:
        parts: list[str] = []
        if missing:
            parts.append(f"inventory factors with no sheet row: {missing}")
        if extra:
            parts.append(f"sheet names missing from inventory: {extra}")
        raise FactorSheetError(
            "Factors CSV does not match inventory — " + "; ".join(parts)
        )


def load_factor_sheet(
    csv_path: Path,
    inventory_factors: Sequence[str] | None = None,
) -> list[FactorRow]:
    """Load the Factor-node sheet; optionally require exact inventory coverage."""
    if not csv_path.is_file():
        raise FactorSheetError(f"Factors CSV not found: {csv_path}")
    with csv_path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        missing_cols = [c for c in _FACTOR_SHEET_COLUMNS if c not in fieldnames]
        if missing_cols:
            raise FactorSheetError(
                f"Factors CSV {csv_path.name} missing columns: {missing_cols}"
            )
        rows = [FactorRow.from_dict(row) for row in reader]
    if inventory_factors is not None:
        _validate_factor_sheet(rows, inventory_factors)
    return rows
