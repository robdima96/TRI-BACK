"""Auditable data models for the agentic Graph-RAG disposition path.

Every tool call and reasoning step the agent takes is captured here so a
supervisor can reconstruct exactly which ground-truth graph/RAG evidence led to
a disposition. High auditability is one of the two hallucination mitigations in
this package (the other is that tools only ever read the red-flags graph and
Chroma corpus - the agent cannot invent nodes, edges, or citations).
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ToolCall(BaseModel):
    """One tool invocation requested by the agent."""

    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolResult(BaseModel):
    """Result of a tool invocation, with provenance for auditing."""

    name: str
    ok: bool = True
    error: str | None = None
    # Compact, model-facing observation string (bounded length).
    observation: str = ""
    # Structured payload retained for logging / UI (not necessarily shown to LLM).
    data: dict[str, Any] = Field(default_factory=dict)
    # Ground-truth provenance surfaced by the tool.
    factors: list[str] = Field(default_factory=list)
    conditions: list[str] = Field(default_factory=list)
    chunk_ids: list[str] = Field(default_factory=list)


class AgentStep(BaseModel):
    """One reasoning turn: model thought + optional tool call + observation."""

    step: int
    thought: str | None = None
    action: ToolCall | None = None
    result: ToolResult | None = None
    # Raw model text for this step (audit / debugging).
    raw: str | None = None


class AgentTrace(BaseModel):
    """Full auditable record of an agentic disposition run."""

    mode: Literal["agentic"] = "agentic"
    status: Literal["ok", "fallback", "error"] = "ok"
    stop_reason: str = ""
    disposition_mode: str = "agentic"
    max_steps: int = 0
    steps_taken: int = 0
    # Tools the agent was offered.
    available_tools: list[str] = Field(default_factory=list)
    steps: list[AgentStep] = Field(default_factory=list)
    # Union of provenance touched across the whole run.
    used_factors: list[str] = Field(default_factory=list)
    used_conditions: list[str] = Field(default_factory=list)
    used_chunk_ids: list[str] = Field(default_factory=list)
    # Unranked ontology membership hits captured at run start (orientation only).
    touched_conditions: list[dict[str, Any]] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)

    def compact(self) -> dict[str, Any]:
        """Trimmed dict for embedding in graph_traversal / session logging."""
        return {
            "mode": self.mode,
            "status": self.status,
            "stop_reason": self.stop_reason,
            "steps_taken": self.steps_taken,
            "max_steps": self.max_steps,
            "available_tools": self.available_tools,
            "used_factors": self.used_factors,
            "used_conditions": self.used_conditions,
            "used_chunk_ids": self.used_chunk_ids,
            "touched_conditions": self.touched_conditions,
            "steps": [
                {
                    "step": s.step,
                    "thought": s.thought,
                    "action": (s.action.name if s.action else None),
                    "action_input": (s.action.arguments if s.action else None),
                    "ok": (s.result.ok if s.result else None),
                    "observation": (s.result.observation if s.result else None),
                    "chunk_ids": (s.result.chunk_ids if s.result else []),
                }
                for s in self.steps
            ],
            "notes": self.notes,
        }
