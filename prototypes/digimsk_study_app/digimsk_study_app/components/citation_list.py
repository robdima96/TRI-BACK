"""Citation chips for evidence chunks."""

from __future__ import annotations

import reflex as rx

from digimsk_study_app.models.chat_types import CitationItem


def _citation_chip(cite: CitationItem) -> rx.Component:
    label = rx.cond(cite["chunk_id"] != "", cite["chunk_id"], cite["source"])
    return rx.box(
        rx.text(label, class_name="citation-chip"),
        rx.text(
            cite["snippet"],
            font_size="0.85rem",
            margin_top="0.35rem",
            color="var(--text-muted-on-light)",
        ),
        margin_bottom="0.35rem",
    )


def citation_list(citations: list[CitationItem]) -> rx.Component:
    return rx.cond(
        citations.length() > 0,
        rx.box(
            rx.foreach(citations, _citation_chip),
            margin_top="0.5rem",
        ),
        rx.fragment(),
    )
