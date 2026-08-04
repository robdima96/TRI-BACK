"""Parse graph_traversal from bot/ ChatResponse."""

from __future__ import annotations

from typing import Protocol

from digimsk_study_app.adapters.base import ChatTurnResult
from digimsk_study_app.graph.schemas import GraphTraversalTrace


class TraversalClient(Protocol):
    def from_chat_response(self, response: ChatTurnResult) -> GraphTraversalTrace | None:
        """Parse graph_traversal dict from bot/ ChatResponse; no local graph query."""


class BotTraversalClient:
    def from_chat_response(self, response: ChatTurnResult) -> GraphTraversalTrace | None:
        raw = response.graph_traversal
        if not raw:
            return None
        try:
            return GraphTraversalTrace.model_validate(raw)
        except Exception:
            return None
