"""Login page — participant and admin forms."""

from __future__ import annotations

import reflex as rx

from digimsk_study_app.state.auth_state import AuthState


def _admin_arm_option(value: str, label: str) -> rx.Component:
    return rx.text(
        rx.hstack(
            rx.radio_group.item(value=value),
            label,
            spacing="2",
            align="center",
        ),
        as_="label",
        size="2",
    )


def login_page() -> rx.Component:
    return rx.box(
        rx.box(
            rx.heading("DigiMSK Study", size="6"),
            rx.text(
                "Musculoskeletal triage chatbot research prototype",
                color="var(--text-muted-on-light)",
                margin_bottom="1rem",
            ),
            rx.tabs.root(
                rx.tabs.list(
                    rx.tabs.trigger("Participant", value="participant"),
                    rx.tabs.trigger("Admin", value="admin"),
                ),
                rx.tabs.content(
                    rx.form(
                        rx.vstack(
                            rx.text("Study ID"),
                            rx.input(name="study_id", placeholder="Your study ID", required=True, width="100%"),
                            rx.text("Password"),
                            rx.input(name="password", type="password", required=True, width="100%"),
                            rx.button("Sign in", type="submit", class_name="btn-primary", width="100%"),
                            rx.cond(
                                AuthState.login_error != "",
                                rx.text(AuthState.login_error, class_name="error-text"),
                            ),
                            spacing="3",
                            width="100%",
                        ),
                        on_submit=AuthState.login_participant_submit,
                        width="100%",
                    ),
                    value="participant",
                ),
                rx.tabs.content(
                    rx.form(
                        rx.vstack(
                            rx.text("Username"),
                            rx.input(name="username", placeholder="admin", required=True, width="100%"),
                            rx.text("Password"),
                            rx.input(name="password", type="password", required=True, width="100%"),
                            rx.text("Preview arm"),
                            rx.radio_group.root(
                                rx.hstack(
                                    _admin_arm_option("1", "Arm 1 (baseline)"),
                                    _admin_arm_option("2", "Arm 2 (reasoning)"),
                                    _admin_arm_option("3", "Arm 3 (graph)"),
                                    class_name="arm-toggle",
                                    wrap="wrap",
                                    spacing="4",
                                ),
                                name="arm",
                                default_value="1",
                                width="100%",
                            ),
                            rx.button("Sign in as admin", type="submit", class_name="btn-primary", width="100%"),
                            rx.cond(
                                AuthState.login_error != "",
                                rx.text(AuthState.login_error, class_name="error-text"),
                            ),
                            spacing="3",
                            width="100%",
                        ),
                        on_submit=AuthState.login_admin_submit,
                        width="100%",
                    ),
                    value="admin",
                ),
                default_value="participant",
                width="100%",
            ),
            class_name="login-card",
        ),
        class_name="login-page",
    )
