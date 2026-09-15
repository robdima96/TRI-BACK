"""TypedDict models for chat UI state (Reflex 0.9 foreach compatibility)."""

from __future__ import annotations

from typing import TypedDict


class CitationItem(TypedDict):
    source: str
    snippet: str
    chunk_id: str
    score: float


class ChatMessageItem(TypedDict):
    message_id: str
    role: str
    content: str
    reasoning_text: str
    graph_json: str
    has_graph: bool
    citations: list[CitationItem]
    timestamp: str
    feedback_rating: str


def normalize_citation(raw: dict) -> CitationItem:
    chunk_id = raw.get("chunk_id")
    return CitationItem(
        source=str(raw.get("source") or ""),
        snippet=str(raw.get("snippet") or ""),
        chunk_id=str(chunk_id) if chunk_id else "",
        score=float(raw.get("score") or 0.0),
    )


def normalize_citations(items: list[dict] | None) -> list[CitationItem]:
    return [normalize_citation(item) for item in (items or [])]


def is_display_citation(item: CitationItem | dict) -> bool:
    """Drop graph/factor debug stubs that are not literature citations."""
    source = str(item.get("source") or "")
    chunk_id = str(item.get("chunk_id") or "")
    if source.startswith("factor:") or source.startswith("graph:"):
        return False
    if "-[" in source:
        return False
    # Bare chunk ids duplicated after titled literature citations.
    if chunk_id and source == chunk_id:
        return False
    if source.startswith("r_") and source[2:].isdigit():
        return False
    return True


def filter_display_citations(items: list[dict] | None) -> list[CitationItem]:
    return [c for c in normalize_citations(items) if is_display_citation(c)]


def empty_message(
    *,
    message_id: str,
    role: str,
    content: str,
    timestamp: str,
    citations: list[CitationItem] | None = None,
    reasoning_text: str = "",
    graph_json: str = "",
    has_graph: bool = False,
    feedback_rating: str = "",
) -> ChatMessageItem:
    return ChatMessageItem(
        message_id=message_id,
        role=role,
        content=content,
        reasoning_text=reasoning_text,
        graph_json=graph_json,
        has_graph=has_graph,
        citations=citations or [],
        timestamp=timestamp,
        feedback_rating=feedback_rating,
    )
