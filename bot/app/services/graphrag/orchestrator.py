"""Controlled graph traversal from checklist items and semantic chunk matches."""

from __future__ import annotations

import logging
import uuid
from pathlib import Path

from app.schemas import ChecklistItem, ChecklistItemDump, ChunkMatch
from app.services.graphrag.condition_traversals import build_condition_traversals
from app.services.graphrag.graph_client_protocol import PathSegment
from app.services.graphrag.local_graph import LocalGraphClient, get_graph_client
from app.services.graphrag.schemas import (
    EdgeRef,
    FactorMatch,
    GraphHighlight,
    GraphTraversalTrace,
    NodeRef,
    TraversalStep,
)
from app.services.rag.factor_matcher import (
    affirmed_factor_names,
    match_checklist_to_factors,
    match_is_affirmed,
)

_log = logging.getLogger(__name__)


def _checklist_rows(
    items: list[ChecklistItem] | list[ChecklistItemDump],
) -> list[ChecklistItemDump]:
    rows: list[ChecklistItemDump] = []
    for item in items:
        if isinstance(item, ChecklistItem):
            rows.append(item.model_dump())
        else:
            rows.append(dict(item))
    return rows


def _node_ref(label: str, name: str, element_id: str | None = None) -> NodeRef:
    from app.services.graphrag.elements import safe_element_id

    safe_id = safe_element_id(element_id) if element_id else None
    return NodeRef(
        label=label,  # type: ignore[arg-type]
        name=name,
        elementId=element_id,
        id=safe_id,
    )


def _edge_ref(
    *,
    rel_type: str,
    source: NodeRef,
    target: NodeRef,
    element_id: str | None = None,
    properties: dict | None = None,
) -> EdgeRef:
    from app.services.graphrag.elements import safe_element_id

    return EdgeRef(
        type=rel_type,
        source=source,
        target=target,
        elementId=element_id,
        id=safe_element_id(element_id) if element_id else None,
        properties=properties or {},
    )


def _segment_steps(
    *,
    start_step: int,
    match: FactorMatch | None,
    segment: PathSegment,
) -> tuple[list[TraversalStep], list[str], list[str]]:
    steps: list[TraversalStep] = []
    node_ids: list[str] = []
    edge_ids: list[str] = []
    step = start_step

    factor_ref = _node_ref("Factor", segment.factor, segment.factor_element_id)
    condition_ref = _node_ref("Condition", segment.condition, segment.condition_element_id)

    checklist_item = match.checklist_item if match else None
    match_method = match.match_method if match else None
    match_score = match.match_score if match else None

    if segment.via_mediation and segment.mediator:
        mediator_ref = _node_ref("Factor", segment.mediator, segment.mediator_element_id)
        step += 1
        traverse_edge = _edge_ref(
            rel_type=segment.relationship,
            source=factor_ref,
            target=mediator_ref,
            element_id=segment.relationship_element_id,
            properties={"path_type": segment.path_type, "via_mediation": True},
        )
        steps.append(
            TraversalStep(
                step=step,
                action="traverse_mediated",
                checklist_item=checklist_item,
                factor=segment.factor,
                mediator=segment.mediator,
                condition=segment.condition,
                relationship=segment.relationship,
                path_type=segment.path_type or "mediated",
                chunk_id=segment.chunk_id or None,
                match_method=match_method,
                match_score=match_score,
                node_refs=[factor_ref, mediator_ref],
                edge_refs=[traverse_edge],
                note=f"{segment.factor} -[{segment.relationship}]-> {segment.mediator}",
            )
        )
        if traverse_edge.id:
            edge_ids.append(traverse_edge.id)
        for ref in (factor_ref, mediator_ref):
            if ref.id:
                node_ids.append(ref.id)

        if segment.contributes_element_id:
            step += 1
            contrib_edge = _edge_ref(
                rel_type="CONTRIBUTES_TO",
                source=mediator_ref,
                target=condition_ref,
                element_id=segment.contributes_element_id,
                properties={"path_type": segment.path_type, "chunk_id": segment.chunk_id},
            )
            steps.append(
                TraversalStep(
                    step=step,
                    action="traverse_mediated",
                    factor=segment.mediator,
                    mediator=segment.mediator,
                    condition=segment.condition,
                    relationship="CONTRIBUTES_TO",
                    path_type=segment.path_type or "mediated",
                    chunk_id=segment.chunk_id or None,
                    node_refs=[mediator_ref, condition_ref],
                    edge_refs=[contrib_edge],
                    note=f"{segment.mediator} -[CONTRIBUTES_TO]-> {segment.condition}",
                )
            )
            if contrib_edge.id:
                edge_ids.append(contrib_edge.id)
    else:
        step += 1
        direct_edge = _edge_ref(
            rel_type=segment.relationship,
            source=factor_ref,
            target=condition_ref,
            element_id=segment.relationship_element_id,
            properties={"path_type": segment.path_type, "via_mediation": False},
        )
        steps.append(
            TraversalStep(
                step=step,
                action="traverse_direct",
                checklist_item=checklist_item,
                factor=segment.factor,
                condition=segment.condition,
                relationship=segment.relationship,
                path_type=segment.path_type or "direct",
                chunk_id=segment.chunk_id or None,
                match_method=match_method,
                match_score=match_score,
                node_refs=[factor_ref, condition_ref],
                edge_refs=[direct_edge],
                note=f"{segment.factor} -[{segment.relationship}]-> {segment.condition}",
            )
        )
        if direct_edge.id:
            edge_ids.append(direct_edge.id)
        for ref in (factor_ref, condition_ref):
            if ref.id:
                node_ids.append(ref.id)

    if segment.chunk_element_id:
        chunk_ref = _node_ref(
            "Chunk", segment.chunk_id or segment.chunk_string[:40], segment.chunk_element_id
        )
        evidence_edges: list[EdgeRef] = []
        if segment.describes_element_id:
            evidence_edges.append(
                _edge_ref(
                    rel_type="DESCRIBES",
                    source=chunk_ref,
                    target=factor_ref,
                    element_id=segment.describes_element_id,
                )
            )
        if segment.applies_element_id:
            evidence_edges.append(
                _edge_ref(
                    rel_type="APPLIES_TO",
                    source=chunk_ref,
                    target=condition_ref,
                    element_id=segment.applies_element_id,
                )
            )
        if evidence_edges:
            step += 1
            steps.append(
                TraversalStep(
                    step=step,
                    action="evidence_link",
                    factor=segment.factor,
                    condition=segment.condition,
                    chunk_id=segment.chunk_id or None,
                    node_refs=[chunk_ref, factor_ref, condition_ref],
                    edge_refs=evidence_edges,
                    note=segment.chunk_string[:160] if segment.chunk_string else segment.chunk_id,
                )
            )
            if chunk_ref.id:
                node_ids.append(chunk_ref.id)
            for edge in evidence_edges:
                if edge.id:
                    edge_ids.append(edge.id)

    return steps, node_ids, edge_ids


def traverse_from_turn(
    *,
    checklist: list[ChecklistItem] | list[ChecklistItemDump],
    chunk_matches: list[ChunkMatch] | None = None,
    factor_matches: list[FactorMatch] | None = None,
    trace_id: str | None = None,
    title: str | None = None,
    graph_client: LocalGraphClient | None = None,
) -> GraphTraversalTrace:
    """Map checklist + chunk seeds to Conditions via local graph."""
    rows = _checklist_rows(checklist)
    tid = trace_id or f"graphrag-{uuid.uuid4().hex[:12]}"
    display_title = title or f"Turn traversal ({len(rows)} checklist items)"

    steps: list[TraversalStep] = []
    highlight_nodes: list[str] = []
    highlight_edges: list[str] = []
    step_num = 0

    for row in rows:
        step_num += 1
        steps.append(
            TraversalStep(
                step=step_num,
                action="checklist_item",
                checklist_item=row,
                note=row.get("text", ""),
            )
        )

    matches = factor_matches or match_checklist_to_factors(rows)
    matched_factors: list[str] = affirmed_factor_names(matches)
    unmatched_items: list[ChecklistItemDump] = []

    for match in matches:
        step_num += 1
        if match_is_affirmed(match):
            factor_ref = _node_ref("Factor", match.factor_name)
            steps.append(
                TraversalStep(
                    step=step_num,
                    action="match_factor",
                    checklist_item=match.checklist_item,
                    factor=match.factor_name,
                    match_method=match.match_method,
                    match_score=match.match_score,
                    node_refs=[factor_ref],
                    note=f"Matched checklist text to Factor '{match.factor_name}'",
                )
            )
        else:
            unmatched_items.append(match.checklist_item)
            denied = match.polarity == "denied"
            steps.append(
                TraversalStep(
                    step=step_num,
                    action="unmatched",
                    checklist_item=match.checklist_item,
                    factor=match.factor_name if denied else None,
                    match_method=match.match_method,
                    match_score=match.match_score,
                    note=(
                        f"Denied Factor '{match.factor_name}' (excluded from traversal)"
                        if denied
                        else "No graph Factor matched this checklist item"
                    ),
                )
            )

    chunk_ids: list[str] = []
    if chunk_matches:
        for cm in chunk_matches:
            step_num += 1
            chunk_ids.append(cm.chunk_id)
            steps.append(
                TraversalStep(
                    step=step_num,
                    action="match_chunk",
                    chunk_id=cm.chunk_id,
                    match_score=cm.score,
                    note=cm.snippet[:160],
                )
            )

    client = graph_client or get_graph_client()
    segments: list[PathSegment] = []
    nodes = []
    edges = []

    if matched_factors or chunk_ids:
        segments = client.paths_for_seeds(matched_factors, chunk_ids)
        nodes, edges = client.build_subgraph(segments)

    factor_to_match = {m.factor_name: m for m in matches if m.factor_name}
    for segment in segments:
        match = factor_to_match.get(segment.factor)
        seg_steps, seg_nodes, seg_edges = _segment_steps(
            start_step=step_num,
            match=match,
            segment=segment,
        )
        steps.extend(seg_steps)
        step_num = steps[-1].step if steps else step_num
        highlight_nodes.extend(seg_nodes)
        highlight_edges.extend(seg_edges)

    condition_risks, condition_traversals, shared_steps = build_condition_traversals(
        segments=segments,
        steps=steps,
        nodes=nodes,
        edges=edges,
    )
    candidate_conditions = [risk.condition for risk in condition_risks]

    if candidate_conditions:
        step_num += 1
        aggregate_step = TraversalStep(
            step=step_num,
            action="aggregate_conditions",
            note=", ".join(candidate_conditions),
        )
        steps.append(aggregate_step)
        shared_steps = [*shared_steps, aggregate_step]

    highlight = GraphHighlight(
        node_ids=list(dict.fromkeys(highlight_nodes)),
        edge_ids=list(dict.fromkeys(highlight_edges)),
    )

    return GraphTraversalTrace(
        trace_id=tid,
        title=display_title,
        checklist_items=rows,
        matched_factors=matched_factors,
        unmatched_items=unmatched_items,
        candidate_conditions=candidate_conditions,
        condition_risks=condition_risks,
        condition_traversals=condition_traversals,
        shared_steps=shared_steps,
        steps=steps,
        highlight=highlight,
        nodes=nodes,
        edges=edges,
    )


def traverse_from_checklist(
    items: list[ChecklistItem] | list[ChecklistItemDump],
    *,
    trace_id: str | None = None,
    title: str | None = None,
    inventory_path: Path | None = None,
    graph_client: LocalGraphClient | None = None,
) -> GraphTraversalTrace:
    """Backward-compatible entry: checklist-only traversal."""
    _ = inventory_path
    return traverse_from_turn(
        checklist=items,
        chunk_matches=None,
        trace_id=trace_id,
        title=title,
        graph_client=graph_client,
    )
