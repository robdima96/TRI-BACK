"""Chat page — shared UI for all arms."""

from __future__ import annotations

import reflex as rx

from tri_back_study_app.components.chat_message import chat_message
from tri_back_study_app.components.typing_indicator import typing_indicator
from tri_back_study_app.state.chat_state import ChatState


def chat_page() -> rx.Component:
    return rx.box(
        rx.box(
            rx.hstack(
                rx.heading("TRI-BACK Study Chat", size="5"),
                rx.spacer(),
                rx.hstack(
                    rx.text("Study ID:", color="var(--text-muted-on-light)"),
                    rx.text(ChatState.study_id, class_name="badge"),
                    rx.text("Session:", color="var(--text-muted-on-light)"),
                    rx.text(ChatState.session_id, class_name="badge"),
                    rx.cond(
                        ChatState.role == "admin",
                        rx.link("Admin dashboard", href="/admin", class_name="btn-secondary"),
                    ),
                    rx.button("Logout", on_click=ChatState.logout, class_name="btn-secondary"),
                    spacing="3",
                    align="center",
                ),
                class_name="topbar",
                width="100%",
            ),
            rx.box(
                rx.cond(
                    ChatState.escalated,
                    rx.box(
                        rx.text(
                            "Important safety notice",
                            font_weight="bold",
                            margin_bottom="0.35rem",
                        ),
                        rx.text(ChatState.safety_reason),
                        class_name="escalation-banner",
                    ),
                ),
                rx.cond(
                    ChatState.error != "",
                    rx.text(ChatState.error, class_name="error-text", margin_bottom="0.5rem"),
                ),
                rx.box(
                    rx.foreach(ChatState.messages, chat_message),
                    rx.cond(ChatState.loading, typing_indicator(), rx.fragment()),
                    class_name="message-list",
                    min_height="50vh",
                ),
                rx.box(
                    rx.text_area(
                        placeholder="Describe your symptoms… (Enter to send, Shift+Enter for newline)",
                        value=ChatState.draft,
                        on_change=ChatState.set_draft,
                        disabled=ChatState.loading,
                        width="100%",
                    ),
                    rx.button(
                        "Send",
                        on_click=ChatState.send_message,
                        class_name="btn-primary",
                        disabled=ChatState.loading,
                    ),
                    class_name="composer",
                ),
                rx.text(
                    "Not for emergency use. If you have urgent symptoms, contact emergency services.",
                    class_name="footer-disclaimer",
                ),
                class_name="chat-main",
            ),
            class_name="chat-page",
        ),
        on_mount=ChatState.mount_chat,
    )
