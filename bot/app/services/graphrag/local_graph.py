"""In-memory red-flags v1 graph traversal from CSV backup."""

from __future__ import annotations

import hashlib
import re
import threading
from functools import lru_cache
from pathlib import Path

from app.services.graphrag.csv_rows import ChunkRow, load_chunks
from app.services.graphrag.elements import edge_from_record, merge_elements, safe_element_id
from app.services.graphrag.graph_client_protocol import PathSegment
from app.services.graphrag.neo4j_config import DEFAULT_CSV_PATH
from app.services.graphrag.schemas import GraphEdge, GraphNode

_REL_SAFE = re.compile(r"[^A-Z0-9_]")
_CLIENT_LOCK = threading.Lock()
_CLIENT_BY_PATH: dict[str, "LocalGraphClient"] = {}


def _synthetic_element_id(label: str, key: str) -> str:
    digest = hashlib.sha256(f"{label}:{key}".encode("utf-8")).hexdigest()[:16]
    return f"local-{digest}"


def _norm_key(text: str) -> str:
    return text.casefold().strip()


def _sanitize_rel(edge: str) -> str:
    cleaned = edge.strip().upper().replace(" ", "_").replace("-", "_")
    cleaned = _REL_SAFE.sub("", cleaned)
    return cleaned or "RELATED_TO"


def _segment_key(seg: PathSegment) -> tuple[str, str, str, str, str]:
    return (
        seg.factor,
        seg.condition,
        seg.relationship,
        seg.mediator or "",
        seg.chunk_id,
    )


@lru_cache(maxsize=4)
def _load_graph_rows(csv_path: str) -> tuple[ChunkRow, ...]:
    return tuple(load_chunks(Path(csv_path)))


class LocalGraphClient:
    """Traverse the v1 red-flags graph from ``red_flags_manual_failsafe.csv``."""

    def __init__(self, csv_path: Path | None = None) -> None:
        path = csv_path or DEFAULT_CSV_PATH
        self._rows = list(_load_graph_rows(str(path.resolve())))
        self._by_factor: dict[str, list[ChunkRow]] = {}
        self._by_chunk_id: dict[str, ChunkRow] = {}
        for row in self._rows:
            self._by_chunk_id[row.chunk_id] = row
            self._by_factor.setdefault(_norm_key(row.source_nodes), []).append(row)

    def close(self) -> None:
        return None

    def __enter__(self) -> LocalGraphClient:
        return self

    def __exit__(self, *_) -> None:
        self.close()

    def _row_to_segments(self, row: ChunkRow) -> list[PathSegment]:
        factor = row.source_nodes
        condition = row.parent_id
        factor_eid = _synthetic_element_id("Factor", factor)
        condition_eid = _synthetic_element_id("Condition", condition)
        chunk_eid = _synthetic_element_id("Chunk", row.chunk_id)
        rel = _sanitize_rel(row.edges)
        segments: list[PathSegment] = []
        path = row.path if row.path and row.path != "-" else ""

        if row.path_type in {"direct", "both"}:
            segments.append(
                PathSegment(
                    factor=factor,
                    factor_element_id=factor_eid,
                    condition=condition,
                    condition_element_id=condition_eid,
                    relationship=rel,
                    relationship_element_id=_synthetic_element_id(
                        "Rel", f"{factor}|{rel}|{condition}|{row.chunk_id}|direct"
                    ),
                    path_type=row.path_type,
                    via_mediation=False,
                    chunk_id=row.chunk_id,
                    chunk_string=row.chunk_string,
                    chunk_element_id=chunk_eid,
                    describes_element_id=_synthetic_element_id(
                        "Rel", f"DESCRIBES|{row.chunk_id}|{factor}"
                    ),
                    applies_element_id=_synthetic_element_id(
                        "Rel", f"APPLIES_TO|{row.chunk_id}|{condition}"
                    ),
                    is_specific=row.is_specific,
                )
            )

        if path and row.path_type in {"mediated", "both"}:
            mediator_eid = _synthetic_element_id("Factor", path)
            segments.append(
                PathSegment(
                    factor=factor,
                    factor_element_id=factor_eid,
                    condition=condition,
                    condition_element_id=condition_eid,
                    relationship=rel,
                    relationship_element_id=_synthetic_element_id(
                        "Rel", f"{factor}|{rel}|{path}|{row.chunk_id}|med"
                    ),
                    path_type=row.path_type,
                    via_mediation=True,
                    mediator=path,
                    mediator_element_id=mediator_eid,
                    contributes_element_id=_synthetic_element_id(
                        "Rel", f"CONTRIBUTES|{path}|{condition}|{row.chunk_id}"
                    ),
                    chunk_id=row.chunk_id,
                    chunk_string=row.chunk_string,
                    chunk_element_id=chunk_eid,
                    describes_element_id=_synthetic_element_id(
                        "Rel", f"DESCRIBES|{row.chunk_id}|{factor}"
                    ),
                    applies_element_id=_synthetic_element_id(
                        "Rel", f"APPLIES_TO|{row.chunk_id}|{condition}"
                    ),
                    is_specific=row.is_specific,
                )
            )

        return segments

    def paths_for_factors(self, factors: list[str]) -> list[PathSegment]:
        segments: list[PathSegment] = []
        seen: set[tuple[str, str, str, str, str]] = set()
        for name in factors:
            for row in self._by_factor.get(_norm_key(name), []):
                for seg in self._row_to_segments(row):
                    key = _segment_key(seg)
                    if key in seen:
                        continue
                    seen.add(key)
                    segments.append(seg)
        return segments

    def paths_for_chunks(self, chunk_ids: list[str]) -> list[PathSegment]:
        segments: list[PathSegment] = []
        seen: set[tuple[str, str, str, str, str]] = set()
        for cid in chunk_ids:
            row = self._by_chunk_id.get(cid)
            if row is None:
                continue
            for seg in self._row_to_segments(row):
                key = _segment_key(seg)
                if key in seen:
                    continue
                seen.add(key)
                segments.append(seg)
        return segments

    def paths_for_seeds(
        self, factors: list[str], chunk_ids: list[str]
    ) -> list[PathSegment]:
        by_factor = self.paths_for_factors(factors)
        by_chunk = self.paths_for_chunks(chunk_ids)
        seen: set[tuple[str, str, str, str, str]] = set()
        merged: list[PathSegment] = []
        preferred = {(s.factor, s.condition) for s in by_factor} & {
            (s.factor, s.condition) for s in by_chunk
        }

        for seg in by_factor + by_chunk:
            key = _segment_key(seg)
            if key in seen:
                continue
            seen.add(key)
            merged.append(seg)

        if preferred:
            merged.sort(
                key=lambda s: (
                    0 if (s.factor, s.condition) in preferred else 1,
                    s.condition,
                    s.factor,
                )
            )
        return merged

    def build_subgraph(
        self, segments: list[PathSegment]
    ) -> tuple[list[GraphNode], list[GraphEdge]]:
        nodes: list[GraphNode] = []
        edges: list[GraphEdge] = []

        def add_node(eid: str, label: str, name: str, props: dict | None = None) -> None:
            nodes.append(
                GraphNode(
                    id=safe_element_id(eid),
                    elementId=eid,
                    label=label,  # type: ignore[arg-type]
                    name=name,
                    properties=props or {},
                )
            )

        for seg in segments:
            add_node(seg.factor_element_id, "Factor", seg.factor)
            add_node(seg.condition_element_id, "Condition", seg.condition)
            if seg.chunk_element_id and seg.chunk_id:
                add_node(
                    seg.chunk_element_id,
                    "Chunk",
                    seg.chunk_id,
                    {
                        "chunk_id": seg.chunk_id,
                        "chunk_string": seg.chunk_string[:500],
                        "is_specific": seg.is_specific,
                    },
                )
            if seg.mediator and seg.mediator_element_id:
                add_node(seg.mediator_element_id, "Factor", seg.mediator)

            if seg.relationship_element_id:
                target_eid = (
                    seg.mediator_element_id
                    if seg.via_mediation and seg.mediator_element_id
                    else seg.condition_element_id
                )
                edges.append(
                    edge_from_record(
                        element_id=seg.relationship_element_id,
                        rel_type=seg.relationship,
                        start_element_id=seg.factor_element_id,
                        end_element_id=target_eid,
                        properties={
                            "path_type": seg.path_type,
                            "via_mediation": seg.via_mediation,
                        },
                    )
                )
            if seg.contributes_element_id and seg.mediator_element_id:
                edges.append(
                    edge_from_record(
                        element_id=seg.contributes_element_id,
                        rel_type="CONTRIBUTES_TO",
                        start_element_id=seg.mediator_element_id,
                        end_element_id=seg.condition_element_id,
                        properties={"path_type": seg.path_type},
                    )
                )
            if seg.describes_element_id and seg.chunk_element_id:
                edges.append(
                    edge_from_record(
                        element_id=seg.describes_element_id,
                        rel_type="DESCRIBES",
                        start_element_id=seg.chunk_element_id,
                        end_element_id=seg.factor_element_id,
                    )
                )
            if seg.applies_element_id and seg.chunk_element_id:
                edges.append(
                    edge_from_record(
                        element_id=seg.applies_element_id,
                        rel_type="APPLIES_TO",
                        start_element_id=seg.chunk_element_id,
                        end_element_id=seg.condition_element_id,
                    )
                )

        return merge_elements(nodes, edges)


# Process-wide singleton: CSV rows are cached via ``_load_graph_rows``, but
# factor/chunk indexes are rebuilt in ``LocalGraphClient.__init__``. Reuse one
# client per CSV path for the process lifetime.


def get_graph_client(csv_path: Path | None = None) -> LocalGraphClient:
    """Return a process-wide ``LocalGraphClient`` for the given CSV path."""
    path = (csv_path or DEFAULT_CSV_PATH).resolve()
    key = str(path)
    with _CLIENT_LOCK:
        client = _CLIENT_BY_PATH.get(key)
        if client is None:
            client = LocalGraphClient(csv_path=path)
            _CLIENT_BY_PATH[key] = client
        return client


def reset_graph_client_cache() -> None:
    """Drop cached clients (tests / CSV hot-reload)."""
    with _CLIENT_LOCK:
        _CLIENT_BY_PATH.clear()
