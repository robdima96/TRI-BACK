"""Arm 2 reasoning text block."""

from __future__ import annotations

import reflex as rx


def reasoning_block(text: str) -> rx.Component:
    return rx.cond(
        text != "",
        rx.box(
            rx.text("Clinical reasoning", font_weight="bold", color="var(--blue-800)", margin_bottom="0.35rem"),
            rx.text(text, class_name="reasoning-block"),
        ),
        rx.fragment(),
    )
