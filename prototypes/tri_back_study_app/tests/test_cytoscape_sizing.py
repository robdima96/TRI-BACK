"""Structural Cytoscape payloads; presentation sizing lives in TriBackCy JS."""

from __future__ import annotations

from tri_back_study_app.graph.cytoscape_builder import build_cytoscape_elements


class _Node:
    def __init__(self, id: str, name: str, label: str):
        self.id = id
        self.name = name
        self.label = label


def test_build_elements_is_structural_only():
    elements = build_cytoscape_elements(
        nodes=[_Node("c1", "Non-specific Mechanical Cause", "Condition")],
        edges=[],
        highlight_node_ids={"c1"},
    )
    data = elements[0]["data"]
    assert data["id"] == "c1"
    assert data["label"] == "Non-specific Mechanical Cause"
    assert data["nodeType"] == "Condition"
    assert data["highlighted"] is True
    assert data["dimmed"] is False
    assert data["askTarget"] is False
    assert "size" not in data
    assert "textMaxWidth" not in data
    assert "color" not in data
