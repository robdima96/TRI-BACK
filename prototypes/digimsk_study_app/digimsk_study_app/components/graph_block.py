"""Arm 3: per-condition graph traversal debug panel."""

from __future__ import annotations

import reflex as rx


def graph_block(graph_json: str, message_id: str) -> rx.Component:
    return rx.cond(
        graph_json != "",
        rx.box(
            rx.text(
                "Graph traversal (debug)",
                font_weight="bold",
                color="var(--blue-800)",
                margin_bottom="0.35rem",
            ),
            rx.el.div(
                class_name="traversal-debug",
                id=f"traversal-{message_id}",
                **{"data-traversal": graph_json},
            ),
            width="100%",
        ),
        rx.fragment(),
    )
