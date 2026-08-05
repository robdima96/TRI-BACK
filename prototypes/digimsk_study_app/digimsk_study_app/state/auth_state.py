"""Authentication state shared across pages."""

from __future__ import annotations

import reflex as rx

from digimsk_study_app.adapters.http_client import ping_bot_ready
from digimsk_study_app.auth.hydrate import auth_fields_from_session
from digimsk_study_app.auth.session import login_admin, login_participant
from digimsk_study_app.config import (
    LOGIN_RATE_LIMIT,
    LOGIN_RATE_WINDOW_SEC,
    PUBLIC_ACCESS,
    SESSION_COOKIE_MAX_AGE,
)
from digimsk_study_app.session_store import init_session, load_session, save_session


class AuthState(rx.State):
    is_authenticated: bool = False
    study_id: str = ""
    role: str = ""
    group_id: int = 1
    admin_selected_arm: int = 1
    session_id: str = rx.Cookie(
        name="digimsk_sid",
        path="/",
        max_age=SESSION_COOKIE_MAX_AGE,
        secure=True if PUBLIC_ACCESS else None,
        same_site="lax",
    )
    login_count: int = 0
    login_at: str = ""
    login_error: str = ""
    _failed_attempts: list[float] = []

    def _hydrate_from_session_store(self) -> bool:
        if self.is_authenticated and (self.session_id or "").strip():
            return True
        fields = auth_fields_from_session(self.session_id)
        if not fields:
            return False
        self.is_authenticated = bool(fields["is_authenticated"])
        self.study_id = str(fields["study_id"])
        self.role = str(fields["role"])
        self.group_id = int(fields["group_id"])
        self.session_id = str(fields["session_id"])
        self.login_count = int(fields["login_count"])
        self.login_at = str(fields["login_at"])
        return True

    def _ensure_authenticated(self) -> bool:
        if self.is_authenticated and (self.session_id or "").strip():
            return True
        return self._hydrate_from_session_store()

    @rx.event
    def require_login(self):
        if not self._ensure_authenticated():
            return rx.redirect("/")

    @rx.event
    def require_admin(self):
        if not self._ensure_authenticated() or self.role != "admin":
            return rx.redirect("/")

    def _rate_limited(self) -> bool:
        import time

        now = time.time()
        window_start = now - LOGIN_RATE_WINDOW_SEC
        self._failed_attempts = [t for t in self._failed_attempts if t >= window_start]
        return len(self._failed_attempts) >= LOGIN_RATE_LIMIT

    @rx.event(background=True)
    async def ping_bot_warmup(self):
        """Fire-and-forget wake of the bot service (GliNER / Vertex lifespan)."""
        await ping_bot_ready()

    @rx.event
    async def login_participant_submit(self, form_data: dict):
        if self._rate_limited():
            self.login_error = "Too many attempts. Please wait and try again."
            return
        study_id = (form_data.get("study_id") or "").strip()
        password = form_data.get("password") or ""
        result = login_participant(study_id, password)
        if not result.ok:
            import time

            self._failed_attempts.append(time.time())
            self.login_error = result.error or "Invalid credentials"
            return
        self._apply_login(result)
        # Warmup starts immediately; chat mount shows the delayed intro in parallel.
        return [AuthState.ping_bot_warmup, rx.redirect("/chat")]

    @rx.event
    async def login_admin_submit(self, form_data: dict):
        if self._rate_limited():
            self.login_error = "Too many attempts. Please wait and try again."
            return
        username = (form_data.get("username") or "").strip()
        password = form_data.get("password") or ""
        arm_raw = form_data.get("arm") or str(self.admin_selected_arm)
        try:
            selected_arm = int(arm_raw)
        except ValueError:
            selected_arm = self.admin_selected_arm
        result = login_admin(username, password, selected_arm)
        if not result.ok:
            import time

            self._failed_attempts.append(time.time())
            self.login_error = result.error or "Invalid credentials"
            return
        self.admin_selected_arm = selected_arm
        self._apply_login(result)
        return [AuthState.ping_bot_warmup, rx.redirect("/chat")]

    def _apply_login(self, result) -> None:
        self.is_authenticated = True
        self.study_id = result.study_id or ""
        self.role = result.role or ""
        self.group_id = int(result.group_id or 1)
        self.session_id = result.session_id or ""
        self.login_count = int(result.login_count or 1)
        self.login_at = result.login_at or ""
        self.login_error = ""
        init_session(
            self.session_id,
            study_id=self.study_id,
            role=self.role,
            group_id=self.group_id,
            login_count=self.login_count,
            login_at=self.login_at,
        )

    @rx.event
    def set_admin_arm(self, arm: str):
        try:
            self.admin_selected_arm = int(arm)
        except ValueError:
            pass

    @rx.event
    def logout(self):
        # Touch last_active_at on the study overlay, then clear auth cookie/state
        # so admin (or participant) can start a fresh login without a full reload.
        sid = (self.session_id or "").strip()
        if sid:
            session = load_session(sid)
            if session:
                save_session(sid, **session)
        self.is_authenticated = False
        self.study_id = ""
        self.role = ""
        self.group_id = 1
        self.session_id = ""
        self.login_count = 0
        self.login_at = ""
        return rx.redirect("/")
