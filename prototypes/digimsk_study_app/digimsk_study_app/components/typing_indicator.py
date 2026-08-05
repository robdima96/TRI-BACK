"""Smartphone-style typing indicator shown while the bot is processing."""

from __future__ import annotations

import reflex as rx


def typing_indicator() -> rx.Component:
    return rx.box(
        rx.box(
            rx.el.span(class_name="typing-dot"),
            rx.el.span(class_name="typing-dot"),
            rx.el.span(class_name="typing-dot"),
            class_name="typing-dots",
            aria_hidden="true",
        ),
        class_name="bubble-typing",
        role="status",
        aria_label="Bot is typing",
    )
