"""Build Cypher statements from red-flags CSV rows."""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

_REL_SAFE = re.compile(r"[^A-Z0-9_]")


def sanitize_rel_type(edge: str) -> str:
    cleaned = edge.strip().upper().replace(" ", "_").replace("-", "_")
    cleaned = _REL_SAFE.sub("", cleaned)
    return cleaned or "RELATED_TO"


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


_BASE_CYPHER = """
MERGE (factor:Factor {name: $source_nodes})
MERGE (condition:Condition {name: $parent_id})
MERGE (chunk:Chunk {chunk_id: $chunk_id})
SET chunk.chunk_string = $chunk_string,
    chunk.source_rank = $source_rank,
    chunk.edges = $edges,
    chunk.path_type = $path_type,
    chunk.path = $path,
    chunk.is_specific = $is_specific,
    chunk.is_guideline = $is_guideline,
    chunk.evidence = $evidence,
    chunk.evidence_level = $evidence_level,
    chunk.loc = $loc
MERGE (chunk)-[:DESCRIBES]->(factor)
MERGE (chunk)-[:APPLIES_TO]->(condition)
"""


def _row_params(row: ChunkRow) -> dict[str, Any]:
    path = row.path if row.path and row.path != "-" else ""
    return {
        "chunk_id": row.chunk_id,
        "chunk_string": row.chunk_string,
        "source_rank": row.source,
        "loc": row.loc,
        "parent_id": row.parent_id,
        "source_nodes": row.source_nodes,
        "edges": row.edges,
        "path_type": row.path_type,
        "path": path,
        "is_specific": row.is_specific,
        "is_guideline": row.is_guideline,
        "evidence": row.evidence,
        "evidence_level": row.evidence_level,
    }


def iter_import_statements(rows: list[ChunkRow]) -> Iterator[tuple[str, dict[str, Any]]]:
    """Yield (cypher, parameters) pairs — one transaction per CSV row."""
    for row in rows:
        rel_type = sanitize_rel_type(row.edges)
        params = _row_params(row)
        path = params["path"]
        path_type = row.path_type

        parts = [_BASE_CYPHER]

        if path_type in {"direct", "both"}:
            parts.append(
                f"""
                MERGE (factor)-[direct_rel:`{rel_type}`]->(condition)
                SET direct_rel.path_type = $path_type,
                    direct_rel.via_mediation = false,
                    direct_rel.chunk_id = $chunk_id
                """
            )

        if path and path_type in {"mediated", "both"}:
            # path is the mediating clinical concept (same Factor label as source_nodes).
            # It may also appear as source_nodes in other rows (e.g. Osteoporosis).
            parts.append(
                f"""
                MERGE (mediator:Factor {{name: $path}})
                MERGE (factor)-[med_rel:`{rel_type}`]->(mediator)
                SET med_rel.path_type = $path_type,
                    med_rel.via_mediation = true,
                    med_rel.chunk_id = $chunk_id
                MERGE (mediator)-[chain:CONTRIBUTES_TO]->(condition)
                SET chain.path_type = $path_type,
                    chain.chunk_id = $chunk_id
                """
            )

        yield "\n".join(parts), params


SCHEMA_STATEMENTS: list[str] = [
    "CREATE CONSTRAINT factor_name IF NOT EXISTS FOR (n:Factor) REQUIRE n.name IS UNIQUE",
    "CREATE CONSTRAINT condition_name IF NOT EXISTS FOR (n:Condition) REQUIRE n.name IS UNIQUE",
    "CREATE CONSTRAINT chunk_id IF NOT EXISTS FOR (n:Chunk) REQUIRE n.chunk_id IS UNIQUE",
    "CREATE INDEX chunk_specific IF NOT EXISTS FOR (c:Chunk) ON (c.is_specific)",
]
