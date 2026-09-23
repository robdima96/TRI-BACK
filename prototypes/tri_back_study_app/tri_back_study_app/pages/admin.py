"""Admin dashboard."""

from __future__ import annotations

import json

import reflex as rx

from tri_back_study_app.components.logout_button import logout_button
from tri_back_study_app.db import login_events as login_db
from tri_back_study_app.db import users as users_db
from tri_back_study_app.session_store import (
    session_detail_for_current_admin,
    sessions_for_current_admin,
)
from tri_back_study_app.state.auth_state import AuthState


def _session_overview(session: dict) -> dict:
    return {
        "study_id": session.get("study_id"),
        "session_id": session.get("session_id"),
        "group_id": session.get("group_id"),
        "turn_count": session.get("turn_count"),
        "time_on_task_sec": session.get("time_on_task_sec"),
        "feedback_up_count": (session.get("engagement") or {}).get("feedback_up_count"),
        "feedback_down_count": (session.get("engagement") or {}).get("feedback_down_count"),
        "escalated": session.get("escalated"),
        "last_active_at": session.get("last_active_at"),
    }


class AdminState(rx.State):
    users_json: str = "[]"
    logins_json: str = "[]"
    sessions_json: str = "[]"
    group_summary: str = ""
    selected_session_json: str = ""

    async def _own_session_id(self) -> str:
        auth = await self.get_state(AuthState)
        return (auth.session_id or "").strip()

    @rx.event
    async def load_data(self):
        users = users_db.list_users()
        logins = login_db.list_login_events()
        own_id = await self._own_session_id()
        sessions = sessions_for_current_admin(own_id)
        counts = users_db.group_counts()
        self.users_json = json.dumps(users, indent=2)
        self.logins_json = json.dumps(logins, indent=2)
        self.sessions_json = json.dumps(
            [_session_overview(s) for s in sessions],
            indent=2,
        )
        self.group_summary = ", ".join(f"Arm {k}: {v}" for k, v in sorted(counts.items()))
        if sessions:
            self.selected_session_json = json.dumps(sessions[0], indent=2)
        else:
            self.selected_session_json = ""

    @rx.event
    async def select_session(self, session_id: str):
        own_id = await self._own_session_id()
        detail = session_detail_for_current_admin(own_id, session_id)
        self.selected_session_json = json.dumps(detail, indent=2) if detail else ""


def admin_page() -> rx.Component:
    return rx.box(
        rx.box(
            rx.hstack(
                rx.heading("TRI-BACK Admin", size="5"),
                rx.spacer(),
                rx.link("Back to chat", href="/chat", class_name="btn-secondary"),
                logout_button(),
                class_name="topbar",
            ),
            rx.box(
                rx.box(
                    rx.heading("Group summary", size="4"),
                    rx.text(AdminState.group_summary),
                    class_name="admin-card",
                ),
                rx.box(
                    rx.heading("Users", size="4"),
                    rx.code_block(AdminState.users_json, language="json", width="100%"),
                    class_name="admin-card",
                ),
                rx.box(
                    rx.heading("Login history", size="4"),
                    rx.code_block(AdminState.logins_json, language="json", width="100%"),
                    class_name="admin-card",
                ),
                rx.box(
                    rx.heading("Sessions overview", size="4"),
                    rx.code_block(AdminState.sessions_json, language="json", width="100%"),
                    class_name="admin-card",
                ),
                rx.box(
                    rx.heading("Session detail (select from overview session_id)", size="4"),
                    rx.input(
                        placeholder="Paste session_id to inspect",
                        on_change=AdminState.select_session,
                        width="100%",
                        margin_bottom="0.5rem",
                    ),
                    rx.code_block(AdminState.selected_session_json, language="json", width="100%"),
                    class_name="admin-card",
                ),
                class_name="admin-grid",
            ),
            on_mount=[AuthState.require_admin, AdminState.load_data],
        ),
    )
