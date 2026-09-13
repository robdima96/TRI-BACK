"""Arm 3: Cytoscape + per-condition traversal debug payloads.

Presentation (colors, sizing, Cytoscape stylesheet) lives in
``shared/digimsk_cytoscape/digimsk_cytoscape.js`` and is applied in the browser
via ``DigiMskCy.prepareElements`` / ``DigiMskCy.cytoscapeStyle``.
This module only builds structural element data + study orchestration payloads.
"""

from __future__ import annotations

import json
from typing import Any

from digimsk_study_app.graph.schemas import (
    ConditionTraversal,
    GraphTraversalTrace,
    TraversalStep,
)


def format_step_summary(step: TraversalStep) -> str:
    if step.action == "checklist_item" and step.checklist_item:
        return f"Checklist: {step.checklist_item.get('text', '')}"
    if step.action == "match_factor" and step.factor:
        return f"Matched factor: {step.factor}"
    if step.action == "match_chunk" and step.chunk_id:
        return f"Evidence chunk: {step.chunk_id}"
    if step.action == "unmatched" and step.checklist_item:
        return f"No factor match: {step.checklist_item.get('text', '')}"
    if step.action in ("traverse_direct", "traverse_mediated"):
        rel = step.relationship or "linked"
        if step.mediator and step.action == "traverse_mediated":
            return f"{step.factor} -[{rel}]-> {step.mediator} -> {step.condition}"
        return f"{step.factor} -[{rel}]-> {step.condition}"
    if step.action == "evidence_link":
        return step.note or f"Evidence linked to {step.condition or 'path'}"
    if step.action == "aggregate_conditions":
        return step.note or "Ranked candidate conditions"
    if step.action == "ask_factor" and step.factor:
        return step.note or f"Asking about: {step.factor}"
    if step.action == "deny_factor" and step.factor:
        return step.note or f"Denied factor: {step.factor}"
    if step.action == "graph_gap":
        return step.note or "Intake question"
    return step.note or step.action


def _step_payload(step: TraversalStep) -> dict[str, Any]:
    node_ids = [ref.id for ref in step.node_refs if ref.id]
    edge_ids = [ref.id for ref in step.edge_refs if ref.id]
    return {
        "step": step.step,
        "action": step.action,
        "summary": format_step_summary(step),
        "condition": step.condition,
        "factor": step.factor,
        "nodeIds": node_ids,
        "edgeIds": edge_ids,
    }


def build_cytoscape_elements(
    *,
    nodes: list,
    edges: list,
    highlight_node_ids: set[str] | None = None,
    highlight_edge_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Structural Cytoscape elements; presentation fields filled client-side."""
    highlight_nodes = highlight_node_ids or set()
    highlight_edges = highlight_edge_ids or set()
    elements: list[dict[str, Any]] = []

    for node in nodes:
        props = getattr(node, "properties", None) or {}
        polarity = str(props.get("polarity") or "")
        ask_target = bool(props.get("ask_target"))
        elements.append(
            {
                "data": {
                    "id": node.id,
                    "label": node.name,
                    "nodeType": node.label,
                    "highlighted": node.id in highlight_nodes,
                    "polarity": polarity,
                    "askTarget": ask_target,
                    "dimmed": polarity == "denied",
                }
            }
        )

    for edge in edges:
        rel = getattr(edge, "type", "") or ""
        elements.append(
            {
                "data": {
                    "id": edge.id,
                    "source": edge.source,
                    "target": edge.target,
                    "label": rel,
                    "edgeType": rel,
                    "highlighted": edge.id in highlight_edges,
                    "confirmAgainst": rel == "CONFIRM_AGAINST",
                }
            }
        )
    return elements


def build_condition_payload(traversal: ConditionTraversal) -> dict[str, Any]:
    highlight_nodes = set(traversal.highlight.node_ids)
    highlight_edges = set(traversal.highlight.edge_ids)
    return {
        "condition": traversal.condition,
        "riskScore": traversal.risk_score,
        "rank": traversal.rank,
        "pathCount": traversal.path_count,
        "supportingFactors": traversal.supporting_factors,
        "steps": [_step_payload(step) for step in traversal.steps],
        "elements": build_cytoscape_elements(
            nodes=traversal.nodes,
            edges=traversal.edges,
            highlight_node_ids=highlight_nodes,
            highlight_edge_ids=highlight_edges,
        ),
        "highlight": {
            "nodeIds": list(highlight_nodes),
            "edgeIds": list(highlight_edges),
        },
    }


def build_traversal_debug_payload(trace: GraphTraversalTrace | None) -> dict[str, Any]:
    if trace is None:
        return {}

    mode = getattr(trace, "mode", "traversal") or "traversal"
    if trace.condition_traversals:
        return {
            "title": trace.title,
            "traceId": trace.trace_id,
            "mode": mode,
            "sharedSteps": [_step_payload(step) for step in trace.shared_steps],
            "conditions": [
                build_condition_payload(traversal)
                for traversal in trace.condition_traversals
            ],
        }

    shared = trace.shared_steps or trace.steps
    if not trace.nodes:
        if not shared:
            return {}
        return {
            "title": trace.title,
            "traceId": trace.trace_id,
            "mode": mode,
            "sharedSteps": [_step_payload(step) for step in shared],
            "conditions": [],
        }

    return {
        "title": trace.title,
        "traceId": trace.trace_id,
        "mode": mode,
        "sharedSteps": [_step_payload(step) for step in trace.steps],
        "conditions": [
            {
                "condition": name,
                "riskScore": 0.0,
                "rank": idx,
                "pathCount": 0,
                "supportingFactors": trace.matched_factors,
                "steps": [],
                "elements": build_cytoscape_elements(
                    nodes=trace.nodes,
                    edges=trace.edges,
                    highlight_node_ids=set(trace.highlight.node_ids),
                    highlight_edge_ids=set(trace.highlight.edge_ids),
                ),
                "highlight": {
                    "nodeIds": trace.highlight.node_ids,
                    "edgeIds": trace.highlight.edge_ids,
                },
            }
            for idx, name in enumerate(trace.candidate_conditions, start=1)
        ],
    }


def arm3_keyed_payload(
    *,
    intake: GraphTraversalTrace | None,
    disposition: GraphTraversalTrace | None,
) -> dict[str, Any]:
    """Keyed Arm-3 payload so the client can show intake, disposition, or both."""
    intake_payload = build_traversal_debug_payload(intake)
    disposition_payload = build_traversal_debug_payload(disposition)
    if not intake_payload and not disposition_payload:
        return {}
    if intake_payload and disposition_payload:
        mode = "both"
    elif intake_payload:
        mode = "intake_gap"
    else:
        mode = "traversal"
    return {
        "mode": mode,
        "intake": intake_payload or None,
        "disposition": disposition_payload or None,
    }


def arm3_keyed_json(
    *,
    intake: GraphTraversalTrace | None,
    disposition: GraphTraversalTrace | None,
) -> str | None:
    payload = arm3_keyed_payload(intake=intake, disposition=disposition)
    if not payload:
        return None
    return json.dumps(payload, ensure_ascii=False)


def cytoscape_json(trace: GraphTraversalTrace | None) -> str:
    """Backward-compatible single-graph payload (first condition or full trace)."""
    payload = build_traversal_debug_payload(trace)
    if not payload:
        return json.dumps({"elements": [], "highlight": {"nodeIds": [], "edgeIds": []}})
    conditions = payload.get("conditions") or []
    if conditions:
        first = conditions[0]
        return json.dumps(
            {
                "elements": first.get("elements", []),
                "highlight": first.get("highlight", {"nodeIds": [], "edgeIds": []}),
                "title": payload.get("title", ""),
                "candidateConditions": [c["condition"] for c in conditions],
            },
            ensure_ascii=False,
        )
    return json.dumps({"elements": [], "highlight": {"nodeIds": [], "edgeIds": []}})


def traversal_debug_json(trace: GraphTraversalTrace | None) -> str:
    return json.dumps(build_traversal_debug_payload(trace), ensure_ascii=False)
