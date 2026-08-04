"""Graph traversal schemas (mirrors bot/app/services/graphrag/schemas.py)."""

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
    id: str
    elementId: str
    label: GraphNodeLabel
    name: str
    properties: dict[str, Any] = Field(default_factory=dict)


class GraphEdge(BaseModel):
    id: str
    elementId: str
    type: str
    source: str
    target: str
    sourceElementId: str
    targetElementId: str
    properties: dict[str, Any] = Field(default_factory=dict)


class GraphHighlight(BaseModel):
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


class ConditionRisk(BaseModel):
    condition: str
    risk_score: float = Field(ge=0.0)
    path_count: int = Field(ge=0, default=0)


class ConditionTraversal(BaseModel):
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
    trace_id: str
    mode: Literal["traversal"] = "traversal"
    title: str = ""
    graph_version: str = "red_flags/v1"
    matched_factors: list[str] = Field(default_factory=list)
    candidate_conditions: list[str] = Field(default_factory=list)
    condition_risks: list[ConditionRisk] = Field(default_factory=list)
    condition_traversals: list[ConditionTraversal] = Field(default_factory=list)
    shared_steps: list[TraversalStep] = Field(default_factory=list)
    steps: list[TraversalStep] = Field(default_factory=list)
    highlight: GraphHighlight = Field(default_factory=GraphHighlight)
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)

    def to_visualization_payload(self) -> dict[str, Any]:
        return {
            "traceId": self.trace_id,
            "mode": self.mode,
            "title": self.title,
            "graphVersion": self.graph_version,
            "matchedFactors": self.matched_factors,
            "candidateConditions": self.candidate_conditions,
            "conditionRisks": [risk.model_dump() for risk in self.condition_risks],
            "conditionTraversals": [
                traversal.model_dump() for traversal in self.condition_traversals
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
