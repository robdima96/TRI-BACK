"""Shared graph traversal client interface."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.services.graphrag.schemas import GraphEdge, GraphNode


@dataclass
class PathSegment:
    """One traversable link with synthetic element ids for visualization."""

    factor: str
    factor_element_id: str
    condition: str
    condition_element_id: str
    relationship: str
    relationship_element_id: str
    path_type: str
    via_mediation: bool
    mediator: str | None = None
    mediator_element_id: str | None = None
    contributes_element_id: str | None = None
    chunk_id: str = ""
    chunk_string: str = ""
    chunk_element_id: str | None = None
    describes_element_id: str | None = None
    applies_element_id: str | None = None
    is_specific: bool = False


class GraphTraversalClient(Protocol):
    def paths_for_factors(self, factors: list[str]) -> list[PathSegment]: ...

    def paths_for_chunks(self, chunk_ids: list[str]) -> list[PathSegment]: ...

    def paths_for_seeds(
        self, factors: list[str], chunk_ids: list[str]
    ) -> list[PathSegment]: ...

    def build_subgraph(
        self, segments: list[PathSegment]
    ) -> tuple[list[GraphNode], list[GraphEdge]]: ...
