"""Pydantic models for GraphRAG traversal traces (Graphs/app compatible)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

GraphNodeLabel = Literal["Factor", "Condition", "Chunk"]
TraversalAction = Literal[
    "checklist_item",
    "match_factor",
    "match_chunk",
    "unmatched",
    "traverse_direct",
    "traverse_mediated",
    "evidence_link",
    "aggregate_conditions",
]


class GraphNode(BaseModel):
    """Cytoscape-ready node (matches Graphs/app ``graphApi.nodeToJson``)."""

    id: str
    elementId: str
    label: GraphNodeLabel
    name: str
    properties: dict[str, Any] = Field(default_factory=dict)


class GraphEdge(BaseModel):
    """Cytoscape-ready edge (matches Graphs/app ``graphApi.relToJson``)."""

    id: str
    elementId: str
    type: str
    source: str
    target: str
    sourceElementId: str
    targetElementId: str
    properties: dict[str, Any] = Field(default_factory=dict)


class GraphHighlight(BaseModel):
    """Ordered highlight sets for Graphs/app traversal visualization."""

    node_ids: list[str] = Field(default_factory=list)
    edge_ids: list[str] = Field(default_factory=list)


class NodeRef(BaseModel):
    label: GraphNodeLabel
    name: str
    elementId: str | None = None
    id: str | None = None


class EdgeRef(BaseModel):
    type: str
    source: NodeRef
    target: NodeRef
    elementId: str | None = None
    id: str | None = None
    properties: dict[str, Any] = Field(default_factory=dict)


class TraversalStep(BaseModel):
    """One auditable step in the orchestrated graph walk."""

    step: int
    action: TraversalAction
    checklist_item: dict[str, str] | None = None
    factor: str | None = None
    condition: str | None = None
    mediator: str | None = None
    relationship: str | None = None
    path_type: str | None = None
    chunk_id: str | None = None
    match_method: str | None = None
    match_score: float | None = None
    node_refs: list[NodeRef] = Field(default_factory=list)
    edge_refs: list[EdgeRef] = Field(default_factory=list)
    note: str | None = None


class FactorMatch(BaseModel):
    checklist_item: dict[str, str]
    factor_name: str | None = None
    match_method: str = "none"
    match_score: float = 0.0


class ConditionRisk(BaseModel):
    condition: str
    risk_score: float = Field(ge=0.0)
    path_count: int = Field(ge=0, default=0)


class ConditionTraversal(BaseModel):
    """Per-condition path steps, risk score, and subgraph slice."""

    condition: str
    risk_score: float = Field(ge=0.0)
    rank: int = Field(ge=1, default=1)
    path_count: int = Field(ge=0, default=0)
    supporting_factors: list[str] = Field(default_factory=list)
    steps: list[TraversalStep] = Field(default_factory=list)
    highlight: GraphHighlight = Field(default_factory=GraphHighlight)
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)


class GraphTraversalTrace(BaseModel):
    """Full traversal artifact for Graphs/app UI consumption."""

    trace_id: str
    mode: Literal["traversal"] = "traversal"
    title: str
    graph_version: str = "red_flags/v1"
    checklist_items: list[dict[str, str]] = Field(default_factory=list)
    matched_factors: list[str] = Field(default_factory=list)
    unmatched_items: list[dict[str, str]] = Field(default_factory=list)
    candidate_conditions: list[str] = Field(default_factory=list)
    condition_risks: list[ConditionRisk] = Field(default_factory=list)
    condition_traversals: list[ConditionTraversal] = Field(default_factory=list)
    shared_steps: list[TraversalStep] = Field(default_factory=list)
    steps: list[TraversalStep] = Field(default_factory=list)
    highlight: GraphHighlight = Field(default_factory=GraphHighlight)
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)

    def to_visualization_payload(self) -> dict[str, Any]:
        """JSON shape for Graphs/app traversal overlay (nodes, edges, highlight, steps)."""
        return {
            "traceId": self.trace_id,
            "mode": self.mode,
            "title": self.title,
            "graphVersion": self.graph_version,
            "matchedFactors": self.matched_factors,
            "candidateConditions": self.candidate_conditions,
            "conditionRisks": [risk.model_dump() for risk in self.condition_risks],
            "conditionTraversals": [
                {
                    "condition": traversal.condition,
                    "riskScore": traversal.risk_score,
                    "rank": traversal.rank,
                    "pathCount": traversal.path_count,
                    "supportingFactors": traversal.supporting_factors,
                    "steps": [step.model_dump() for step in traversal.steps],
                    "highlight": {
                        "nodeIds": traversal.highlight.node_ids,
                        "edgeIds": traversal.highlight.edge_ids,
                    },
                    "nodes": [node.model_dump() for node in traversal.nodes],
                    "edges": [edge.model_dump() for edge in traversal.edges],
                }
                for traversal in self.condition_traversals
            ],
            "sharedSteps": [step.model_dump() for step in self.shared_steps],
            "steps": [step.model_dump() for step in self.steps],
            "highlight": {
                "nodeIds": self.highlight.node_ids,
                "edgeIds": self.highlight.edge_ids,
            },
            "nodes": [node.model_dump() for node in self.nodes],
            "edges": [edge.model_dump() for edge in self.edges],
        }
