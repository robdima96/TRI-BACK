"""Authentication state shared across pages."""

from __future__ import annotations

import asyncio

import reflex as rx

from tri_back_study_app.adapters.http_client import ping_bot_ready
from tri_back_study_app.auth.hydrate import auth_fields_from_token
from tri_back_study_app.auth.logout import (
    LOGOUT_CONFIRM_TIMEOUT_SEC,
    should_complete_logout,
    should_disarm_logout,
    stamp_session_json,
)
from tri_back_study_app.auth.session import login_admin, login_participant
from tri_back_study_app.config import (
    LOGIN_RATE_LIMIT,
    LOGIN_RATE_WINDOW_SEC,
    PUBLIC_ACCESS,
    SESSION_COOKIE_MAX_AGE,
)
from tri_back_study_app.db.auth_tokens import create_token, get_valid_token, revoke_token
from tri_back_study_app.session_store import init_session


class AuthState(rx.State):
    admin_selected_arm: int = 1
    auth_token: str = rx.Cookie(
        name="tri_back_sid",
        path="/",
        max_age=SESSION_COOKIE_MAX_AGE,
        secure=True if PUBLIC_ACCESS else None,
        same_site="lax",
    )
    login_error: str = ""
    logout_confirming: bool = False
    _logout_arm_id: int = 0
    _failed_attempts: list[float] = []
    _is_authenticated: bool = False
    _study_id: str = ""
    _role: str = ""
    _group_id: int = 1
    _session_file_id: str = ""
    _login_count: int = 0
    _login_at: str = ""

    @rx.var
    def is_authenticated(self) -> bool:
        return bool(self._is_authenticated)

    @rx.var
    def study_id(self) -> str:
        return self._study_id

    @rx.var
    def role(self) -> str:
        return self._role

    @rx.var
    def group_id(self) -> int:
        return int(self._group_id or 1)

    @rx.var
    def session_id(self) -> str:
        """Session file id for display. Never the cookie token."""
        return self._session_file_id

    @rx.var
    def login_count(self) -> int:
        return int(self._login_count or 0)

    @rx.var
    def login_at(self) -> str:
        return self._login_at

    def _file_id(self) -> str:
        return (self._session_file_id or "").strip()

    def _apply_token_fields(self, fields: dict) -> None:
        self._is_authenticated = True
        self._study_id = str(fields.get("study_id") or "")
        self._role = str(fields.get("role") or "")
        self._group_id = int(fields.get("group_id") or 1)
        self._session_file_id = str(fields.get("session_id") or "")
        self._login_count = int(fields.get("login_count") or 0)
        self._login_at = str(fields.get("login_at") or "")

    def _hydrate_from_token(self) -> bool:
        fields = auth_fields_from_token(self.auth_token)
        if not fields:
            self._clear_identity()
            return False
        self._apply_token_fields(fields)
        return True

    def _ensure_authenticated(self) -> bool:
        row = get_valid_token(self.auth_token)
        if not row:
            self._clear_identity()
            return False
        return self._hydrate_from_token()

    def _clear_identity(self) -> None:
        self._is_authenticated = False
        self._study_id = ""
        self._role = ""
        self._group_id = 1
        self._session_file_id = ""
        self._login_count = 0
        self._login_at = ""

    @rx.event
    def require_login(self):
        if not self._ensure_authenticated():
            return rx.redirect("/")

    @rx.event
    def require_admin(self):
        if not self._ensure_authenticated() or self._role != "admin":
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
        from tri_back_study_app.state.chat_state import ChatState

        return [AuthState.ping_bot_warmup, ChatState.mount_chat, rx.redirect("/chat")]

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
        from tri_back_study_app.state.chat_state import ChatState

        return [AuthState.ping_bot_warmup, ChatState.mount_chat, rx.redirect("/chat")]

    def _apply_login(self, result) -> None:
        file_id = result.session_id or ""
        init_session(
            file_id,
            study_id=result.study_id or "",
            role=result.role or "",
            group_id=int(result.group_id or 1),
            login_count=int(result.login_count or 1),
            login_at=result.login_at or "",
        )
        token = create_token(
            study_id=result.study_id or "",
            role=result.role or "",
            session_file_id=file_id,
        )
        self.auth_token = token
        self._apply_token_fields(
            {
                "study_id": result.study_id or "",
                "role": result.role or "",
                "group_id": int(result.group_id or 1),
                "session_id": file_id,
                "login_count": int(result.login_count or 1),
                "login_at": result.login_at or "",
            }
        )
        self.login_error = ""
        self.logout_confirming = False
        self._logout_arm_id = 0

    @rx.event
    def set_admin_arm(self, arm: str):
        try:
            self.admin_selected_arm = int(arm)
        except ValueError:
            pass

    def _end_session(self) -> None:
        """Revoke the cookie token and stamp the session file."""
        stamp_session_json(self._file_id())
        revoke_token(self.auth_token)
        self.auth_token = ""
        self._clear_identity()
        self.login_error = ""
        self.logout_confirming = False
        self._logout_arm_id = 0

    def _arm_logout_confirm(self) -> int:
        self.logout_confirming = True
        self._logout_arm_id += 1
        return self._logout_arm_id

    @rx.event(background=True)
    async def disarm_logout_confirm(self, arm_id: int):
        """Restore the idle Logout button if the confirm click never comes."""
        await asyncio.sleep(float(LOGOUT_CONFIRM_TIMEOUT_SEC))
        async with self:
            if should_disarm_logout(self.logout_confirming, self._logout_arm_id, arm_id):
                self.logout_confirming = False

    @rx.event
    def request_logout(self):
        """First click arms; second click ends the session with no delay."""
        if not should_complete_logout(self.logout_confirming):
            arm_id = self._arm_logout_confirm()
            return AuthState.disarm_logout_confirm(arm_id)
        self._end_session()
        return rx.redirect("/")

    @rx.event
    def logout(self):
        """Immediate teardown (same as the confirmed second click)."""
        self._end_session()
        return rx.redirect("/")
