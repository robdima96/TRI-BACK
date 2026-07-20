"""Group graph traversal steps and subgraph slices per candidate condition."""

from __future__ import annotations

from app.services.graphrag.condition_ranker import score_conditions
from app.services.graphrag.graph_client_protocol import PathSegment
from app.services.graphrag.schemas import (
    ConditionRisk,
    ConditionTraversal,
    GraphEdge,
    GraphHighlight,
    GraphNode,
    TraversalStep,
)

_SHARED_ACTIONS = frozenset(
    {
        "checklist_item",
        "match_factor",
        "match_chunk",
        "unmatched",
        "aggregate_conditions",
    }
)
_CONDITION_ACTIONS = frozenset(
    {"traverse_direct", "traverse_mediated", "evidence_link"}
)


def _refs_from_steps(steps: list[TraversalStep]) -> tuple[list[str], list[str]]:
    node_ids: list[str] = []
    edge_ids: list[str] = []
    for step in steps:
        for ref in step.node_refs:
            if ref.id:
                node_ids.append(ref.id)
        for ref in step.edge_refs:
            if ref.id:
                edge_ids.append(ref.id)
    return list(dict.fromkeys(node_ids)), list(dict.fromkeys(edge_ids))


def _filter_subgraph(
    nodes: list[GraphNode],
    edges: list[GraphEdge],
    *,
    node_ids: set[str],
    edge_ids: set[str],
) -> tuple[list[GraphNode], list[GraphEdge]]:
    kept_nodes = [n for n in nodes if n.id in node_ids]
    kept_node_set = {n.id for n in kept_nodes}
    kept_edges = [
        e
        for e in edges
        if e.id in edge_ids
        or (e.source in kept_node_set and e.target in kept_node_set)
    ]
    return kept_nodes, kept_edges


def build_condition_traversals(
    *,
    segments: list[PathSegment],
    steps: list[TraversalStep],
    nodes: list[GraphNode],
    edges: list[GraphEdge],
) -> tuple[list[ConditionRisk], list[ConditionTraversal], list[TraversalStep]]:
    """Partition traversal artifacts by ranked candidate condition."""
    risks = score_conditions(segments)
    shared_steps = [s for s in steps if s.action in _SHARED_ACTIONS]

    traversals: list[ConditionTraversal] = []
    for rank, risk in enumerate(risks, start=1):
        cond = risk.condition
        cond_segments = [s for s in segments if s.condition == cond]
        supporting_factors = sorted({s.factor for s in cond_segments if s.factor})

        path_steps = [s for s in steps if s.condition == cond and s.action in _CONDITION_ACTIONS]
        factor_steps = [
            s
            for s in steps
            if s.action == "match_factor" and s.factor in supporting_factors
        ]
        merged_steps = sorted(
            {s.step: s for s in (*factor_steps, *path_steps)}.values(),
            key=lambda s: s.step,
        )

        highlight_nodes, highlight_edges = _refs_from_steps(merged_steps)
        highlight = GraphHighlight(
            node_ids=highlight_nodes,
            edge_ids=highlight_edges,
        )
        cond_nodes, cond_edges = _filter_subgraph(
            nodes,
            edges,
            node_ids=set(highlight_nodes),
            edge_ids=set(highlight_edges),
        )

        traversals.append(
            ConditionTraversal(
                condition=cond,
                risk_score=risk.risk_score,
                rank=rank,
                path_count=risk.path_count,
                supporting_factors=supporting_factors,
                steps=merged_steps,
                highlight=highlight,
                nodes=cond_nodes,
                edges=cond_edges,
            )
        )

    return risks, traversals, shared_steps
