"""GraphRAG: checklist-driven traversal of the red-flags knowledge graph."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from app.services.graphrag.neo4j_config import DEFAULT_GRAPHS_ENV, Neo4jConfig
from app.services.graphrag.schemas import GraphTraversalTrace

if TYPE_CHECKING:
    from app.services.graphrag.local_graph import LocalGraphClient

__all__ = [
    "DEFAULT_GRAPHS_ENV",
    "GraphTraversalTrace",
    "LocalGraphClient",
    "Neo4jConfig",
    "get_graph_client",
    "graphrag_configured",
    "load_factor_names",
    "match_checklist_to_factors",
    "traverse_from_checklist",
    "traverse_from_turn",
]


def graphrag_configured(env_path: Path | None = None) -> bool:
    """True when local v1 CSV graph is available (always for default backup path)."""
    from app.services.graphrag.neo4j_config import DEFAULT_CSV_PATH

    return DEFAULT_CSV_PATH.is_file()


def load_factor_names(*args, **kwargs):
    from app.services.graphrag.factor_matcher import load_factor_names as _fn

    return _fn(*args, **kwargs)


def match_checklist_to_factors(*args, **kwargs):
    from app.services.graphrag.factor_matcher import match_checklist_to_factors as _fn

    return _fn(*args, **kwargs)


def traverse_from_checklist(*args, **kwargs):
    from app.services.graphrag.orchestrator import traverse_from_checklist as _fn

    return _fn(*args, **kwargs)


def traverse_from_turn(*args, **kwargs):
    from app.services.graphrag.orchestrator import traverse_from_turn as _fn

    return _fn(*args, **kwargs)


def get_graph_client(*args, **kwargs):
    from app.services.graphrag.local_graph import get_graph_client as _fn

    return _fn(*args, **kwargs)


def __getattr__(name: str):
    if name == "LocalGraphClient":
        from app.services.graphrag.local_graph import LocalGraphClient

        return LocalGraphClient
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
