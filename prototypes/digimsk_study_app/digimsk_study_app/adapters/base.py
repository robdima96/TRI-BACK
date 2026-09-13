"""Shared adapter types."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class ChatTurnResult:
    session_id: str
    response: str
    citations: list[dict[str, Any]] = field(default_factory=list)
    escalated: bool = False
    safety_reason: str | None = None
    question_mode: bool = False
    questions_asked: int = 0
    coverage_ready: bool = False
    graph_traversal: dict[str, Any] | None = None
    intake_traversal: dict[str, Any] | None = None
    matched_factors: list[str] = field(default_factory=list)
    candidate_conditions: list[str] = field(default_factory=list)
    traversed_chunk_ids: list[str] = field(default_factory=list)
    clinical_checklist: list[dict[str, Any]] = field(default_factory=list)
    extraction_history: list[dict[str, Any]] = field(default_factory=list)
    turn_extraction: dict[str, Any] | None = None
    reasoning_text: str | None = None
    graph_json: str | None = None
    has_graph: bool = False
    round_trip_ms: float = 0.0


class ChatbotAdapter(Protocol):
    async def send_message(self, session_id: str, message: str) -> ChatTurnResult: ...
