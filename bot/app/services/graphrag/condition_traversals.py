"""Group graph traversal steps and subgraph slices per candidate condition."""

from __future__ import annotations

import uuid

from app.services.graphrag.graph_client_protocol import PathSegment
from app.services.graphrag.inference import get_condition_scorer
from app.services.graphrag.schemas import (
    ConditionRisk,
    ConditionTraversal,
    GraphEdge,
    GraphHighlight,
    GraphNode,
    GraphTraversalTrace,
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
    risks = get_condition_scorer().score(segments)
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


def build_agent_provenance_trace(
    *,
    checklist: list[dict[str, str]],
    used_factors: list[str],
    used_conditions: list[str],
    factors_by_condition: dict[str, tuple[str, ...]],
    title: str,
    max_paths_per_condition: int = 6,
) -> GraphTraversalTrace:
    """Build an Arm-3 audit graph from agent-touched entities without scoring.

    Condition order follows the agent trace. ``risk_score`` is deliberately
    zero because this artifact records provenance, not deterministic or
    probabilistic inference.
    """
    from app.services.graphrag.local_graph import get_graph_client
    from app.services.graphrag.orchestrator import _segment_steps

    client = get_graph_client()
    factors = list(dict.fromkeys(f for f in used_factors if f))
    conditions = list(dict.fromkeys(c for c in used_conditions if c))
    condition_set = set(conditions)

    segments: list[PathSegment] = []
    if factors:
        segments.extend(client.paths_for_factors(factors))
    segments = [
        segment
        for segment in _dedupe_segments(segments)
        if not condition_set or segment.condition in condition_set
    ]

    present = {segment.condition for segment in segments}
    for condition in conditions:
        if condition in present:
            continue
        seeds = list(factors_by_condition.get(condition) or ())
        extra = [
            segment
            for segment in client.paths_for_factors(seeds)
            if segment.condition == condition
        ][:max_paths_per_condition]
        segments.extend(extra)
    segments = _dedupe_segments(segments)

    all_nodes, all_edges = client.build_subgraph(segments)
    steps: list[TraversalStep] = []
    traversals: list[ConditionTraversal] = []
    all_node_ids: list[str] = []
    all_edge_ids: list[str] = []
    step_num = 0

    for rank, condition in enumerate(conditions, start=1):
        cond_segments = [s for s in segments if s.condition == condition]
        cond_steps: list[TraversalStep] = []
        cond_node_ids: list[str] = []
        cond_edge_ids: list[str] = []
        for segment in cond_segments:
            built, node_ids, edge_ids = _segment_steps(
                start_step=step_num,
                match=None,
                segment=segment,
            )
            cond_steps.extend(built)
            steps.extend(built)
            if built:
                step_num = built[-1].step
            cond_node_ids.extend(node_ids)
            cond_edge_ids.extend(edge_ids)
        cond_node_ids = list(dict.fromkeys(cond_node_ids))
        cond_edge_ids = list(dict.fromkeys(cond_edge_ids))
        all_node_ids.extend(cond_node_ids)
        all_edge_ids.extend(cond_edge_ids)
        cond_nodes, cond_edges = _filter_subgraph(
            all_nodes,
            all_edges,
            node_ids=set(cond_node_ids),
            edge_ids=set(cond_edge_ids),
        )
        traversals.append(
            ConditionTraversal(
                condition=condition,
                risk_score=0.0,
                rank=rank,
                path_count=len(cond_segments),
                supporting_factors=sorted(
                    {s.factor for s in cond_segments if s.factor}
                ),
                steps=cond_steps,
                highlight=GraphHighlight(
                    node_ids=cond_node_ids,
                    edge_ids=cond_edge_ids,
                ),
                nodes=cond_nodes,
                edges=cond_edges,
            )
        )

    return GraphTraversalTrace(
        trace_id=f"agentic-{uuid.uuid4().hex[:12]}",
        title=title,
        checklist_items=list(checklist),
        matched_factors=factors,
        candidate_conditions=conditions,
        condition_traversals=traversals,
        steps=steps,
        highlight=GraphHighlight(
            node_ids=list(dict.fromkeys(all_node_ids)),
            edge_ids=list(dict.fromkeys(all_edge_ids)),
        ),
        nodes=all_nodes,
        edges=all_edges,
    )


def _dedupe_segments(segments: list[PathSegment]) -> list[PathSegment]:
    seen: set[tuple[str, str, str, str]] = set()
    out: list[PathSegment] = []
    for seg in segments:
        key = (
            seg.factor or "",
            seg.condition or "",
            seg.chunk_id or "",
            seg.relationship or "",
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(seg)
    return out


def ensure_conditions_in_trace(
    trace: GraphTraversalTrace,
    conditions: list[str],
    *,
    preferred_factors: list[str] | None = None,
    factors_by_condition: dict[str, tuple[str, ...]] | None = None,
    max_paths_per_condition: int = 6,
) -> GraphTraversalTrace:
    """Ensure listed conditions appear as Arm-3 display traversals.

    After agentic disposition, conditions the agent inspected (for example
    Non-specific Mechanical Cause) should surface even when deterministic
    matching only ranked a weaker red-flag candidate. Prefer paths grounded in
    matched checklist factors; otherwise attach a compact evidence slice.
    """
    from app.services.graphrag.local_graph import get_graph_client
    from app.services.graphrag.orchestrator import _segment_steps
    from app.services.graphrag.schemas import GraphTraversalTrace as TraceModel

    if not conditions:
        return trace

    existing = {c.condition for c in trace.condition_traversals}
    missing = [c for c in dict.fromkeys(conditions) if c and c not in existing]
    if not missing:
        return trace

    client = get_graph_client()
    preferred = list(dict.fromkeys(preferred_factors or trace.matched_factors or []))
    factor_map = factors_by_condition or {}

    segments: list[PathSegment] = []
    if preferred:
        segments.extend(client.paths_for_factors(preferred))

    for condition in missing:
        seeds = list(factor_map.get(condition) or ())
        grounded = [f for f in seeds if f in set(preferred)] if preferred else []
        if grounded:
            segs = [
                s for s in client.paths_for_factors(grounded) if s.condition == condition
            ]
        elif seeds:
            segs = [
                s for s in client.paths_for_factors(seeds) if s.condition == condition
            ][:max_paths_per_condition]
        else:
            segs = []
        segments.extend(segs)

    segments = _dedupe_segments(segments)
    if not any(s.condition in missing for s in segments):
        return trace

    nodes, edges = client.build_subgraph(segments)
    step_num = max((s.step for s in trace.steps), default=0)
    new_steps: list[TraversalStep] = list(trace.steps)
    for segment in segments:
        if segment.condition not in missing:
            continue
        seg_steps, _, _ = _segment_steps(
            start_step=step_num,
            match=None,
            segment=segment,
        )
        new_steps.extend(seg_steps)
        if seg_steps:
            step_num = seg_steps[-1].step

    risks, traversals, shared_steps = build_condition_traversals(
        segments=segments,
        steps=new_steps,
        nodes=nodes,
        edges=edges,
    )

    # Keep prior traversals that fell out of the rebuilt segment set.
    by_name = {t.condition: t for t in traversals}
    risk_by_name = {r.condition: r for r in risks}
    for prior in trace.condition_traversals:
        if prior.condition in by_name:
            continue
        by_name[prior.condition] = prior
        risk_by_name[prior.condition] = ConditionRisk(
            condition=prior.condition,
            risk_score=prior.risk_score,
            path_count=prior.path_count,
        )

    ordered_risks = sorted(
        risk_by_name.values(), key=lambda r: (-r.risk_score, r.condition)
    )
    ranked: list[ConditionTraversal] = []
    for rank, risk in enumerate(ordered_risks, start=1):
        prior = by_name.get(risk.condition)
        if prior is None:
            continue
        ranked.append(
            prior.model_copy(update={"rank": rank, "risk_score": risk.risk_score})
        )

    return TraceModel(
        trace_id=trace.trace_id,
        mode=trace.mode,
        title=trace.title,
        graph_version=trace.graph_version,
        checklist_items=trace.checklist_items,
        matched_factors=trace.matched_factors,
        unmatched_items=trace.unmatched_items,
        candidate_conditions=[r.condition for r in ordered_risks],
        condition_risks=ordered_risks,
        condition_traversals=ranked,
        shared_steps=shared_steps or trace.shared_steps,
        steps=new_steps,
        highlight=trace.highlight,
        nodes=nodes,
        edges=edges,
    )
