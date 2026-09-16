"""Arm-3 View B: intake planner slice from session factor state + real CSV edges.

The payload reuses ``GraphTraversalTrace`` with ``mode="intake_gap"``. Edges come
only from the v4 edges CSV (plus the mediated ``CONTRIBUTES_TO`` continuation
already produced by ``LocalGraphClient``). Factor-sheet columns are node
metadata, never relationships.
"""

from __future__ import annotations

import uuid
from typing import Any

from app.services.agentic_graph_rag.ontology import RedFlagOntology, load_ontology
from app.services.graphrag.condition_traversals import _dedupe_segments, _filter_subgraph
from app.services.graphrag.elements import safe_element_id
from app.services.graphrag.graph_client_protocol import PathSegment
from app.services.graphrag.local_graph import get_graph_client
from app.services.graphrag.schemas import (
    ConditionTraversal,
    EdgeRef,
    GraphEdge,
    GraphHighlight,
    GraphNode,
    GraphTraversalTrace,
    NodeRef,
    TraversalStep,
)
from app.services.rag.factor_polarity import (
    FACTOR_STATE_AFFIRMED,
    FACTOR_STATE_DENIED,
    FACTOR_STATE_UNKNOWN,
)

# Mediated factor → mediator uses the CSV relationship; mediator → condition
# is the existing LocalGraphClient continuation, not a factors-CSV column.
_MEDIATED_CONTINUATION = "CONTRIBUTES_TO"
_CHUNK_REL_TYPES = frozenset({"DESCRIBES", "APPLIES_TO"})
_FACTOR_SHEET_COLUMNS = frozenset({"askable", "intent", "fallback", "synonyms"})


def csv_relationship_types(ontology: RedFlagOntology | None = None) -> frozenset[str]:
    """Relationship types defined on the edges CSV, plus mediated continuation."""
    ont = ontology or load_ontology()
    return frozenset(ont.relations) | {_MEDIATED_CONTINUATION}


def allowed_intake_edge_types(ontology: RedFlagOntology | None = None) -> frozenset[str]:
    return csv_relationship_types(ontology)


def _canonical(name: str, ontology: RedFlagOntology) -> str | None:
    spec = ontology.get_factor_question_spec(name)
    if spec is not None:
        return spec.factor
    want = name.casefold().strip()
    for factor in ontology.all_factors:
        if factor.casefold() == want:
            return factor
    return None


def _state_of(factor_states: dict[str, str] | None, factor: str) -> str:
    raw = (factor_states or {}).get(factor) or FACTOR_STATE_UNKNOWN
    if raw in {FACTOR_STATE_AFFIRMED, FACTOR_STATE_DENIED, FACTOR_STATE_UNKNOWN}:
        return raw
    return FACTOR_STATE_UNKNOWN


def _node_ref(label: str, name: str, element_id: str | None = None) -> NodeRef:
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
    return EdgeRef(
        type=rel_type,
        source=source,
        target=target,
        elementId=element_id,
        id=safe_element_id(element_id) if element_id else None,
        properties=properties or {},
    )


def _factors_by_polarity(
    factor_states: dict[str, str] | None,
    *,
    ontology: RedFlagOntology,
) -> tuple[list[str], list[str]]:
    affirmed: list[str] = []
    denied: list[str] = []
    seen: set[str] = set()
    for raw, polarity in (factor_states or {}).items():
        canonical = _canonical(raw, ontology)
        if not canonical or canonical in seen:
            continue
        seen.add(canonical)
        if polarity == FACTOR_STATE_AFFIRMED:
            affirmed.append(canonical)
        elif polarity == FACTOR_STATE_DENIED:
            denied.append(canonical)
    return affirmed, denied


def _drop_chunk_artifacts(
    nodes: list[GraphNode],
    edges: list[GraphEdge],
    *,
    allowed_types: frozenset[str],
) -> tuple[list[GraphNode], list[GraphEdge]]:
    kept_edges = [
        edge
        for edge in edges
        if edge.type in allowed_types
        and edge.type not in _CHUNK_REL_TYPES
        and edge.type not in _FACTOR_SHEET_COLUMNS
    ]
    kept_ids = {n.id for n in nodes if n.label != "Chunk"}
    connected: set[str] = set()
    usable_edges: list[GraphEdge] = []
    for edge in kept_edges:
        if edge.source in kept_ids and edge.target in kept_ids:
            connected.add(edge.source)
            connected.add(edge.target)
            usable_edges.append(edge)
    kept_nodes = [n for n in nodes if n.id in connected]
    return kept_nodes, usable_edges


def _annotate_nodes(
    nodes: list[GraphNode],
    *,
    factor_states: dict[str, str] | None,
    ask_target: str | None,
    ontology: RedFlagOntology,
) -> list[GraphNode]:
    out: list[GraphNode] = []
    for node in nodes:
        props = dict(node.properties or {})
        if node.label == "Factor":
            canonical = _canonical(node.name, ontology) or node.name
            polarity = _state_of(factor_states, canonical)
            spec = ontology.get_factor_question_spec(canonical)
            is_target = bool(ask_target and canonical == ask_target)
            if is_target and polarity == FACTOR_STATE_UNKNOWN:
                polarity = FACTOR_STATE_UNKNOWN
            props["polarity"] = polarity
            props["ask_target"] = is_target
            props["askable"] = bool(spec.askable) if spec is not None else False
            if is_target and spec is not None and not spec.askable:
                # Planner must not highlight a non-askable mediator as the ask.
                props["ask_target"] = False
        out.append(node.model_copy(update={"properties": props}))
    return out


def _segment_edge_steps(
    *,
    start_step: int,
    segment: PathSegment,
) -> tuple[list[TraversalStep], list[str], list[str]]:
    """Path steps for View B — CSV relationships only, no chunk DESCRIBES links."""
    steps: list[TraversalStep] = []
    node_ids: list[str] = []
    edge_ids: list[str] = []
    step = start_step
    factor_ref = _node_ref("Factor", segment.factor, segment.factor_element_id)
    condition_ref = _node_ref("Condition", segment.condition, segment.condition_element_id)
    if factor_ref.id:
        node_ids.append(factor_ref.id)
    if condition_ref.id:
        node_ids.append(condition_ref.id)

    if segment.via_mediation and segment.mediator and segment.mediator_element_id:
        mediator_ref = _node_ref("Factor", segment.mediator, segment.mediator_element_id)
        if mediator_ref.id:
            node_ids.append(mediator_ref.id)
        step += 1
        rel_edge = _edge_ref(
            rel_type=segment.relationship,
            source=factor_ref,
            target=mediator_ref,
            element_id=segment.relationship_element_id,
        )
        steps.append(
            TraversalStep(
                step=step,
                action="traverse_mediated",
                factor=segment.factor,
                condition=segment.condition,
                mediator=segment.mediator,
                relationship=segment.relationship,
                path_type=segment.path_type,
                node_refs=[factor_ref, mediator_ref, condition_ref],
                edge_refs=[rel_edge],
            )
        )
        if rel_edge.id:
            edge_ids.append(rel_edge.id)
        if segment.contributes_element_id:
            step += 1
            contrib = _edge_ref(
                rel_type=_MEDIATED_CONTINUATION,
                source=mediator_ref,
                target=condition_ref,
                element_id=segment.contributes_element_id,
            )
            steps.append(
                TraversalStep(
                    step=step,
                    action="traverse_mediated",
                    factor=segment.mediator,
                    condition=segment.condition,
                    relationship=_MEDIATED_CONTINUATION,
                    path_type=segment.path_type,
                    node_refs=[mediator_ref, condition_ref],
                    edge_refs=[contrib],
                )
            )
            if contrib.id:
                edge_ids.append(contrib.id)
    else:
        step += 1
        rel_edge = _edge_ref(
            rel_type=segment.relationship,
            source=factor_ref,
            target=condition_ref,
            element_id=segment.relationship_element_id,
        )
        steps.append(
            TraversalStep(
                step=step,
                action="traverse_direct",
                factor=segment.factor,
                condition=segment.condition,
                relationship=segment.relationship,
                path_type=segment.path_type,
                node_refs=[factor_ref, condition_ref],
                edge_refs=[rel_edge],
            )
        )
        if rel_edge.id:
            edge_ids.append(rel_edge.id)
    return steps, node_ids, edge_ids


def build_intake_gap_trace(
    *,
    factor_states: dict[str, str] | None,
    asked_factor: str | None,
    question_reason: str | None,
    slot_being_asked: str | None = None,
    title: str = "Intake planner slice",
    ontology: RedFlagOntology | None = None,
    graph_csv=None,
) -> GraphTraversalTrace:
    """Build the accumulating planner subgraph for a question turn."""
    ont = ontology or load_ontology()
    affirmed, denied = _factors_by_polarity(factor_states, ontology=ont)
    ask_target = _canonical(asked_factor or "", ont) if asked_factor else None
    if ask_target:
        spec = ont.get_factor_question_spec(ask_target)
        if spec is None or not spec.askable:
            ask_target = None

    seed_names = list(dict.fromkeys([*affirmed, *denied, *([ask_target] if ask_target else [])]))
    client = get_graph_client(csv_path=graph_csv)
    segments: list[PathSegment] = []
    if seed_names:
        segments = _dedupe_segments(client.paths_for_factors(seed_names))

    allowed = allowed_intake_edge_types(ont)
    all_nodes, all_edges = client.build_subgraph(segments) if segments else ([], [])
    all_nodes, all_edges = _drop_chunk_artifacts(all_nodes, all_edges, allowed_types=allowed)
    all_nodes = _annotate_nodes(
        all_nodes,
        factor_states=factor_states,
        ask_target=ask_target,
        ontology=ont,
    )

    steps: list[TraversalStep] = []
    shared: list[TraversalStep] = []
    step_num = 0
    for factor in affirmed:
        step_num += 1
        node = next((n for n in all_nodes if n.label == "Factor" and n.name == factor), None)
        refs = [_node_ref("Factor", factor, node.elementId if node else None)]
        step = TraversalStep(
            step=step_num,
            action="match_factor",
            factor=factor,
            node_refs=refs,
            note=f"Affirmed factor '{factor}'",
        )
        steps.append(step)
        shared.append(step)
    for factor in denied:
        step_num += 1
        node = next((n for n in all_nodes if n.label == "Factor" and n.name == factor), None)
        refs = [_node_ref("Factor", factor, node.elementId if node else None)]
        step = TraversalStep(
            step=step_num,
            action="deny_factor",
            factor=factor,
            node_refs=refs,
            note=f"Denied factor '{factor}'",
        )
        steps.append(step)
        shared.append(step)

    reason = (question_reason or "").strip()
    if ask_target:
        step_num += 1
        node = next((n for n in all_nodes if n.label == "Factor" and n.name == ask_target), None)
        refs = [_node_ref("Factor", ask_target, node.elementId if node else None)]
        step = TraversalStep(
            step=step_num,
            action="ask_factor",
            factor=ask_target,
            node_refs=refs,
            note=reason or f"Ask factor '{ask_target}'",
        )
        steps.append(step)
        shared.append(step)
    elif slot_being_asked or reason:
        step_num += 1
        step = TraversalStep(
            step=step_num,
            action="graph_gap",
            note=reason or f"Ask slot '{slot_being_asked}'",
        )
        steps.append(step)
        shared.append(step)

    traversals: list[ConditionTraversal] = []
    highlight_nodes: list[str] = []
    highlight_edges: list[str] = []
    conditions = list(dict.fromkeys(seg.condition for seg in segments if seg.condition))
    for rank, condition in enumerate(conditions, start=1):
        cond_segments = [s for s in segments if s.condition == condition]
        cond_steps: list[TraversalStep] = []
        cond_node_ids: list[str] = []
        cond_edge_ids: list[str] = []
        for segment in cond_segments:
            built, node_ids, edge_ids = _segment_edge_steps(
                start_step=step_num,
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
        highlight_nodes.extend(cond_node_ids)
        highlight_edges.extend(cond_edge_ids)
        supporting = sorted(
            {
                s.factor
                for s in cond_segments
                if s.factor in set(affirmed) or s.factor == ask_target
            }
        )
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
                supporting_factors=supporting,
                steps=cond_steps,
                highlight=GraphHighlight(node_ids=cond_node_ids, edge_ids=cond_edge_ids),
                nodes=cond_nodes,
                edges=cond_edges,
            )
        )

    ask_node_ids = [
        n.id
        for n in all_nodes
        if n.label == "Factor" and bool((n.properties or {}).get("ask_target"))
    ]
    if ask_node_ids:
        highlight_nodes = list(dict.fromkeys([*ask_node_ids, *highlight_nodes]))

    return GraphTraversalTrace(
        trace_id=f"intake-{uuid.uuid4().hex[:12]}",
        mode="intake_gap",
        title=title,
        graph_version=ont.graph_version,
        matched_factors=list(affirmed),
        candidate_conditions=conditions,
        condition_traversals=traversals,
        shared_steps=shared,
        steps=steps,
        highlight=GraphHighlight(
            node_ids=list(dict.fromkeys(highlight_nodes)),
            edge_ids=list(dict.fromkeys(highlight_edges)),
        ),
        nodes=all_nodes,
        edges=all_edges,
    )


def intake_trace_from_state(state: dict[str, Any]) -> GraphTraversalTrace:
    from app.triage_profiles import load_ontology_for_profile, profile_from_state

    profile = profile_from_state(state)
    return build_intake_gap_trace(
        factor_states=state.get("factor_states"),
        asked_factor=state.get("asked_factor"),
        question_reason=state.get("question_reason"),
        slot_being_asked=state.get("slot_being_asked"),
        title=f"Intake planner: {state.get('session_id', '')}",
        ontology=load_ontology_for_profile(profile),
        graph_csv=profile.graph_csv,
    )


def final_intake_trace_from_state(state: dict[str, Any]) -> GraphTraversalTrace:
    """Accumulated interview neighbourhood with no live ask target.

    Built at disposition / escalate so Arm 3 can show the question path once,
    after advice, without highlighting a factor that was already answered.
    """
    from app.triage_profiles import load_ontology_for_profile, profile_from_state

    profile = profile_from_state(state)
    return build_intake_gap_trace(
        factor_states=state.get("factor_states"),
        asked_factor=None,
        question_reason=None,
        slot_being_asked=None,
        title=f"Intake path: {state.get('session_id', '')}",
        ontology=load_ontology_for_profile(profile),
        graph_csv=profile.graph_csv,
    )


def rendered_relationship_types(trace: GraphTraversalTrace) -> set[str]:
    return {edge.type for edge in trace.edges}


def assert_intake_edges_are_csv_backed(
    trace: GraphTraversalTrace,
    *,
    ontology: RedFlagOntology | None = None,
) -> None:
    allowed = allowed_intake_edge_types(ontology)
    unexpected = rendered_relationship_types(trace) - allowed
    if unexpected:
        raise AssertionError(
            f"intake_gap rendered relationship types not in edges CSV: {sorted(unexpected)}"
        )


def highlighted_factor_names(trace: GraphTraversalTrace) -> list[str]:
    highlighted = set(trace.highlight.node_ids)
    names: list[str] = []
    for node in trace.nodes:
        if node.id in highlighted and node.label == "Factor":
            if (node.properties or {}).get("ask_target"):
                names.append(node.name)
    return names
