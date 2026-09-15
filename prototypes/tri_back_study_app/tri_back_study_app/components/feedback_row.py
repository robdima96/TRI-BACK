"""Thumbs up/down feedback row."""

from __future__ import annotations

import reflex as rx

from tri_back_study_app.state.chat_state import ChatState


def feedback_row(message_id: str, rating: str) -> rx.Component:
    up_cls = rx.cond(rating == "up", "feedback-btn selected-up", "feedback-btn")
    down_cls = rx.cond(rating == "down", "feedback-btn selected-down", "feedback-btn")
    return rx.hstack(
        rx.button(
            "👍",
            class_name=up_cls,
            aria_label="Helpful",
            on_click=ChatState.rate_message(message_id, "up"),
        ),
        rx.button(
            "👎",
            class_name=down_cls,
            aria_label="Not helpful",
            on_click=ChatState.rate_message(message_id, "down"),
        ),
        class_name="feedback-row",
        spacing="2",
    )
