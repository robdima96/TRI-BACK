"""Toggleable agentic Graph-RAG disposition path for TRI-BACK.

Enabled with ``TRI_BACK_DISPOSITION_MODE=agentic`` (legacy ``TRI_BACK_DISPOSITION_MODE``; default ``deterministic``).
RAG and GraphRAG tools are exposed independently by their evidence toggles.
The agent starts from factor matching plus an unranked ontology-membership tally;
it does not consume deterministic traversal/ranking unless its own run fails.
Separate hand-editable frameworks cover graph-tool and traditional-RAG runs.

Lazy imports keep heavy dependencies (generator backends, graph client) off the
module-import path, matching ``app.services.graphrag``.
"""

from __future__ import annotations

__all__ = [
    "agentic_disposition_node",
    "load_ontology",
    "get_factor_question_spec",
    "render_ontology_card",
    "run_disposition_agent",
    "FRAMEWORK_PATH",
]


def agentic_disposition_node(*args, **kwargs):
    from app.services.agentic_graph_rag.node import agentic_disposition_node as _fn

    return _fn(*args, **kwargs)


def run_disposition_agent(*args, **kwargs):
    from app.services.agentic_graph_rag.agent import run_disposition_agent as _fn

    return _fn(*args, **kwargs)


def load_ontology(*args, **kwargs):
    from app.services.agentic_graph_rag.ontology import load_ontology as _fn

    return _fn(*args, **kwargs)


def get_factor_question_spec(*args, **kwargs):
    from app.services.agentic_graph_rag.ontology import get_factor_question_spec as _fn

    return _fn(*args, **kwargs)


def render_ontology_card(*args, **kwargs):
    from app.services.agentic_graph_rag.ontology import render_ontology_card as _fn

    return _fn(*args, **kwargs)


def __getattr__(name: str):
    if name == "FRAMEWORK_PATH":
        from app.services.agentic_graph_rag.prompt_template import FRAMEWORK_PATH

        return FRAMEWORK_PATH
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
