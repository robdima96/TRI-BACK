"""Serialize Neo4j nodes/relationships for Graphs/app Cytoscape JSON."""

from __future__ import annotations

import re
from typing import Any

from app.services.graphrag.schemas import GraphEdge, GraphNode, GraphNodeLabel

_SAFE_ID_RE = re.compile(r"[^a-zA-Z0-9]")


def safe_element_id(element_id: str) -> str:
    """Mirror ``Graphs/app/lib/graphApi.js`` safeElementId."""
    return f"n_{_SAFE_ID_RE.sub('_', str(element_id))}"


def _serialize_value(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "toNumber"):
        return value.toNumber()
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def serialize_properties(props: dict[str, Any] | None) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in (props or {}).items():
        out[key] = _serialize_value(value)
    return out


def primary_label(labels: list[str]) -> GraphNodeLabel:
    if "Condition" in labels:
        return "Condition"
    if "Chunk" in labels:
        return "Chunk"
    if "Factor" in labels:
        return "Factor"
    return labels[0] if labels else "Factor"  # type: ignore[return-value]


def node_display_name(props: dict[str, Any], label: str) -> str:
    return str(props.get("name") or props.get("chunk_id") or label)


def node_from_record(
    *,
    element_id: str,
    labels: list[str],
    properties: dict[str, Any],
) -> GraphNode:
    label = primary_label(labels)
    return GraphNode(
        id=safe_element_id(element_id),
        elementId=element_id,
        label=label,
        name=node_display_name(properties, label),
        properties=serialize_properties(properties),
    )


def edge_from_record(
    *,
    element_id: str,
    rel_type: str,
    start_element_id: str,
    end_element_id: str,
    properties: dict[str, Any] | None = None,
) -> GraphEdge:
    return GraphEdge(
        id=safe_element_id(element_id),
        elementId=element_id,
        type=rel_type,
        source=safe_element_id(start_element_id),
        target=safe_element_id(end_element_id),
        sourceElementId=start_element_id,
        targetElementId=end_element_id,
        properties=serialize_properties(properties),
    )


def merge_elements(
    nodes: list[GraphNode],
    edges: list[GraphEdge],
) -> tuple[list[GraphNode], list[GraphEdge]]:
    node_map: dict[str, GraphNode] = {}
    edge_map: dict[str, GraphEdge] = {}
    for node in nodes:
        node_map[node.id] = node
    for edge in edges:
        edge_map[edge.id] = edge
    return list(node_map.values()), list(edge_map.values())
