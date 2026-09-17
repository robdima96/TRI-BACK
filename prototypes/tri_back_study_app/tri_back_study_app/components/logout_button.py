"""In-place two-click logout control (chat and admin)."""

from __future__ import annotations

import reflex as rx

from tri_back_study_app.auth.logout import LOGOUT_CONFIRM_LABEL, LOGOUT_LABEL
from tri_back_study_app.state.chat_state import ChatState


def logout_button() -> rx.Component:
    return rx.button(
        rx.cond(
            ChatState.logout_confirming,
            LOGOUT_CONFIRM_LABEL,
            LOGOUT_LABEL,
        ),
        on_click=ChatState.request_logout,
        class_name=rx.cond(
            ChatState.logout_confirming,
            "btn-logout-confirm",
            "btn-secondary",
        ),
    )
