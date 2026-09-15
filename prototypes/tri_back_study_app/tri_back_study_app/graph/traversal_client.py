"""Parse graph_traversal / intake_traversal from bot/ ChatResponse."""

from __future__ import annotations

from typing import Any, Protocol

from tri_back_study_app.adapters.base import ChatTurnResult
from tri_back_study_app.graph.schemas import GraphTraversalTrace


def parse_traversal_payload(raw: dict[str, Any] | None) -> GraphTraversalTrace | None:
    if not raw:
        return None
    try:
        return GraphTraversalTrace.model_validate(raw)
    except Exception:
        return None


class TraversalClient(Protocol):
    def from_chat_response(self, response: ChatTurnResult) -> GraphTraversalTrace | None:
        """Parse graph_traversal dict from bot/ ChatResponse; no local graph query."""


class BotTraversalClient:
    def from_chat_response(self, response: ChatTurnResult) -> GraphTraversalTrace | None:
        """Parse the disposition subgraph (View A)."""
        return parse_traversal_payload(response.graph_traversal)

    def intake_from_chat_response(
        self, response: ChatTurnResult
    ) -> GraphTraversalTrace | None:
        """Parse the intake planner slice (View B)."""
        return parse_traversal_payload(getattr(response, "intake_traversal", None))
