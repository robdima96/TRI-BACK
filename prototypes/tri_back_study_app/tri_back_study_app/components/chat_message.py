"""Chat message bubble with arm-specific optional blocks."""

from __future__ import annotations

import reflex as rx

from tri_back_study_app.components.feedback_row import feedback_row
from tri_back_study_app.components.graph_block import graph_block
from tri_back_study_app.components.reasoning_block import reasoning_block
from tri_back_study_app.models.chat_types import ChatMessageItem


def chat_message(msg: ChatMessageItem) -> rx.Component:
    # Citations (r_38, titled evidence chips, etc.) stay in session JSON for
    # analysis but are not shown in the participant chat UI.
    return rx.cond(
        msg["role"] == "user",
        rx.box(rx.text(msg["content"]), class_name="bubble-user"),
        rx.box(
            rx.text(msg["content"]),
            reasoning_block(msg["reasoning_text"]),
            graph_block(msg["graph_json"], msg["message_id"]),
            feedback_row(msg["message_id"], msg["feedback_rating"]),
            class_name="bubble-assistant",
        ),
    )
