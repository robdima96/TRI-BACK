"""Parse red-flags v1 CSV rows (mirrors ``Graphs/graph_builder.py``)."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path


def _boolish(value: str) -> bool:
    return value.strip().lower() in {"yes", "true", "1"}


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
