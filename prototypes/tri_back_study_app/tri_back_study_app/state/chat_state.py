"""Chat page state."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

import reflex as rx

from tri_back_study_app.adapters.presentation import get_presentation_adapter
from tri_back_study_app.config import (
    IDLE_TIMEOUT_SEC,
    INTRO_DELAY_SEC,
    INTRO_MESSAGE,
    INTRO_MESSAGE_ID,
)
from tri_back_study_app.auth.logout import should_complete_logout
from tri_back_study_app.models.chat_types import (
    ChatMessageItem,
    CitationItem,
    empty_message,
    normalize_citations,
)
from tri_back_study_app.session_store import load_session, save_session
from tri_back_study_app.state.auth_state import AuthState
from tri_back_study_app.state.engagement_tracker import (
    EngagementTracker,
    feedback_tallies,
    recompute_engagement,
    word_char_counts,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _messages_to_session(messages: list[ChatMessageItem]) -> list[dict]:
    out: list[dict] = []
    for m in messages:
        out.append(
            {
                "message_id": m["message_id"],
                "role": m["role"],
                "content": m["content"],
                "reasoning_text": m["reasoning_text"] or None,
                "graph_json": m["graph_json"] or None,
                "has_graph": m["has_graph"],
                "citations": m["citations"],
                "timestamp": m["timestamp"],
                "feedback": {
                    "rating": m["feedback_rating"] or None,
                    "rated_at": None,
                },
                "question_mode": bool(m.get("question_mode")),
                "rephrased": bool(m.get("rephrased")),
            }
        )
    return out


def _session_messages_to_chat(items: list[dict] | None) -> list[ChatMessageItem]:
    out: list[ChatMessageItem] = []
    for raw in items or []:
        if not isinstance(raw, dict):
            continue
        feedback = raw.get("feedback") or {}
        graph_json = str(raw.get("graph_json") or "")
        out.append(
            empty_message(
                message_id=str(raw.get("message_id") or ""),
                role=str(raw.get("role") or ""),
                content=str(raw.get("content") or ""),
                timestamp=str(raw.get("timestamp") or ""),
                reasoning_text=str(raw.get("reasoning_text") or ""),
                graph_json=graph_json,
                has_graph=bool(raw.get("has_graph")) or bool(graph_json),
                citations=normalize_citations(raw.get("citations")),
                feedback_rating=str(feedback.get("rating") or ""),
                question_mode=bool(raw.get("question_mode")),
                rephrased=bool(raw.get("rephrased")),
            )
        )
    return out


def should_play_intro(messages: list[ChatMessageItem] | list[dict]) -> bool:
    """True when this session has no transcript yet (intro not shown)."""
    return len(messages) == 0


AUTH_HYDRATE_RETRY_SEC = 0.2


def intro_mount_action(
    *,
    authenticated: bool,
    messages: list[ChatMessageItem] | list[dict],
    after_retry: bool = False,
) -> str:
    """How ``mount_chat`` should proceed: retry, redirect, play, or skip."""
    if not authenticated:
        return "redirect" if after_retry else "retry"
    if should_play_intro(messages):
        return "play"
    return "skip"


def build_intro_message(*, timestamp: str | None = None) -> ChatMessageItem:
    """Study-local welcome bubble (never posted to ``POST /api/v1/chat``)."""
    return empty_message(
        message_id=INTRO_MESSAGE_ID,
        role="assistant",
        content=INTRO_MESSAGE,
        timestamp=timestamp or _now_iso(),
    )


def chat_view_from_session(session: dict | None) -> dict:
    """Transcript fields for the chat UI. Missing session wipes leftovers."""
    if not session:
        return {
            "messages": [],
            "turn_count": 0,
            "escalated": False,
            "safety_reason": "",
        }
    return {
        "messages": _session_messages_to_chat(session.get("messages")),
        "turn_count": int(session.get("turn_count") or 0),
        "escalated": bool(session.get("escalated")),
        "safety_reason": str(session.get("safety_reason") or ""),
    }


class ChatState(AuthState):
    messages: list[ChatMessageItem] = []
    draft: str = ""
    loading: bool = False
    error: str = ""
    escalated: bool = False
    safety_reason: str = ""
    turn_count: int = 0

    @staticmethod
    def _merge_citations(
        existing: list[dict], new_items: list[dict]
    ) -> list[CitationItem]:
        seen: set[str] = set()
        merged: list[CitationItem] = []
        for item in normalize_citations(existing) + normalize_citations(new_items):
            key = item["chunk_id"] or item["source"] or item["snippet"]
            if key in seen:
                continue
            seen.add(key)
            merged.append(item)
        return merged

    def _load_chat_from_session(self) -> None:
        fields = chat_view_from_session(load_session(self._file_id()))
        self.messages = fields["messages"]
        self.turn_count = fields["turn_count"]
        self.escalated = fields["escalated"]
        self.safety_reason = fields["safety_reason"]

    def _clear_chat_ui(self) -> None:
        self.messages = []
        self.draft = ""
        self.loading = False
        self.error = ""
        self.escalated = False
        self.safety_reason = ""
        self.turn_count = 0

    @rx.event
    def request_logout(self):
        if not should_complete_logout(self.logout_confirming):
            arm_id = self._arm_logout_confirm()
            return ChatState.disarm_logout_confirm(arm_id)
        self._clear_chat_ui()
        self._end_session()
        return rx.redirect("/")

    @rx.event
    def logout(self):
        self._clear_chat_ui()
        self._end_session()
        return rx.redirect("/")

    def _persist_messages(self) -> None:
        session = load_session(self._file_id()) or {}
        engagement = session.get("engagement") or {}
        msg_dicts = _messages_to_session(self.messages)
        up, down = feedback_tallies(msg_dicts)
        engagement = dict(engagement)
        engagement["feedback_up_count"] = up
        engagement["feedback_down_count"] = down
        save_session(
            self._file_id(),
            study_id=self.study_id,
            role=self.role,
            group_id=self.group_id,
            login_count=self.login_count,
            login_at=self.login_at,
            turn_count=self.turn_count,
            messages=msg_dicts,
            engagement=engagement,
        )

    @rx.event(background=True)
    async def mount_chat(self):
        async with self:
            ready = self._ensure_authenticated()
            if ready:
                self._load_chat_from_session()
            action = intro_mount_action(
                authenticated=ready,
                messages=self.messages if ready else [],
            )

        if action == "retry":
            await asyncio.sleep(AUTH_HYDRATE_RETRY_SEC)
            async with self:
                ready = self._ensure_authenticated()
                if ready:
                    self._load_chat_from_session()
                action = intro_mount_action(
                    authenticated=ready,
                    messages=self.messages if ready else [],
                    after_retry=True,
                )
            if action == "redirect":
                yield rx.redirect("/")
                return

        if action != "play":
            return

        async with self:
            # Typing bubble while the intentional delay runs (warmup started at login).
            self.loading = True
            self.error = ""

        await asyncio.sleep(float(INTRO_DELAY_SEC))

        async with self:
            if not self._ensure_authenticated():
                self.loading = False
                return
            # Another tab / remount may have written the intro already.
            self._load_chat_from_session()
            if not should_play_intro(self.messages):
                self.loading = False
                return
            self.messages = [build_intro_message()]
            self._persist_messages()
            self.loading = False

    @rx.event
    def set_draft(self, value: str):
        self.draft = value

    @rx.event(background=True)
    async def send_message(self):
        async with self:
            if not self._ensure_authenticated():
                self.error = "Session expired. Please log in again."
                return
            text = (self.draft or "").strip()
            if not text or self.loading:
                return

            tracker = EngagementTracker(IDLE_TIMEOUT_SEC)
            self.loading = True
            self.error = ""
            tracker.note_idle_before_turn()
            words, chars = word_char_counts(text)
            turn_index = self.turn_count
            user_msg = empty_message(
                message_id=f"msg_{turn_index:03d}_u",
                role="user",
                content=text,
                timestamp=_now_iso(),
            )
            self.messages = [*self.messages, user_msg]
            self.draft = ""

            session_id = self._file_id()
            group_id = self.group_id
            study_id = self.study_id
            role = self.role
            login_count = self.login_count
            login_at = self.login_at

        try:
            adapter = get_presentation_adapter(group_id)
            result = await adapter.send_message(session_id, text)
        except Exception as exc:
            async with self:
                self.error = f"Could not reach chatbot backend: {exc}"
                self.loading = False
            return

        async with self:
            assistant = empty_message(
                message_id=f"msg_{turn_index:03d}",
                role="assistant",
                content=result.response,
                timestamp=_now_iso(),
                reasoning_text=result.reasoning_text or "",
                graph_json=result.graph_json or "",
                has_graph=result.has_graph,
                citations=normalize_citations(result.citations),
                question_mode=bool(result.question_mode),
            )
            self.messages = [*self.messages, assistant]
            self.turn_count = turn_index + 1
            self.escalated = result.escalated
            self.safety_reason = result.safety_reason or ""

            session = load_session(session_id) or {}
            engagement = session.get("engagement") or {"turns": []}
            engagement.setdefault("turns", []).append(
                {
                    "turn_index": self.turn_count,
                    "timestamp": _now_iso(),
                    "user_word_count": words,
                    "user_char_count": chars,
                    "composer_to_send_ms": 0.0,
                    "round_trip_ms": result.round_trip_ms,
                    "idle_before_turn_sec": tracker.idle_before_turn_sec(),
                }
            )
            time_on_task = tracker.time_on_task_sec()
            engagement = recompute_engagement(engagement, time_on_task_sec=time_on_task)
            msg_dicts = _messages_to_session(self.messages)
            up, down = feedback_tallies(msg_dicts)
            engagement["feedback_up_count"] = up
            engagement["feedback_down_count"] = down

            # Clinical / disposition fields are written by the bot API into the
            # same bot/data/sessions file. Study UI only patches engagement +
            # study metadata so disposition audits are never wiped.
            save_session(
                session_id,
                study_id=study_id,
                role=role,
                group_id=group_id,
                login_count=login_count,
                login_at=login_at,
                turn_count=self.turn_count,
                time_on_task_sec=time_on_task,
                messages=msg_dicts,
                engagement=engagement,
                citations=self._merge_citations(
                    session.get("citations") or [], result.citations
                ),
            )
            self.loading = False

    @rx.event
    def rate_message(self, message_id: str, rating: str):
        if not self._ensure_authenticated():
            return
        if rating not in ("up", "down"):
            return
        # Prefer the live UI transcript so feedback sticks even when the shared
        # session file was briefly overwritten by a concurrent bot save.
        updated: list[ChatMessageItem] = []
        found = False
        for msg in self.messages:
            if msg["message_id"] == message_id:
                updated.append({**msg, "feedback_rating": rating})
                found = True
            else:
                updated.append(msg)
        if not found:
            return
        self.messages = updated

        messages = _messages_to_session(self.messages)
        for msg in messages:
            if msg.get("message_id") == message_id:
                msg["feedback"] = {"rating": rating, "rated_at": _now_iso()}
        engagement = (load_session(self._file_id()) or {}).get("engagement") or {}
        up, down = feedback_tallies(messages)
        engagement = recompute_engagement(
            engagement,
            time_on_task_sec=float(engagement.get("session_duration_sec") or 0.0),
        )
        engagement["feedback_up_count"] = up
        engagement["feedback_down_count"] = down
        try:
            save_session(self._file_id(), messages=messages, engagement=engagement)
        except OSError:
            # Keep the in-memory rating. GCS FUSE can refuse overlay writes
            # without the clinical transcript being lost.
            logging.getLogger(__name__).warning(
                "feedback save failed session=%s message_id=%s",
                self._file_id(),
                message_id,
                exc_info=True,
            )
        self.error = ""

    @rx.event(background=True)
    async def rephrase_message(self, message_id: str):
        async with self:
            if not self._ensure_authenticated():
                self.error = "Session expired. Please log in again."
                return
            if self.loading:
                return
            target = None
            for msg in self.messages:
                if msg["message_id"] == message_id:
                    target = msg
                    break
            if target is None or target.get("rephrased") or not target.get("question_mode"):
                return
            self.loading = True
            self.error = ""
            session_id = self._file_id()
            group_id = self.group_id

        try:
            adapter = get_presentation_adapter(group_id)
            result = await adapter.rephrase_message(session_id, message_id)
        except Exception as exc:
            async with self:
                self.error = f"Could not rephrase that question: {exc}"
                self.loading = False
            return

        async with self:
            updated: list[ChatMessageItem] = []
            for msg in self.messages:
                if msg["message_id"] == message_id:
                    updated.append(
                        {
                            **msg,
                            "content": result.response or msg["content"],
                            "rephrased": True,
                        }
                    )
                else:
                    updated.append(msg)
            self.messages = updated
            try:
                save_session(session_id, messages=_messages_to_session(self.messages))
            except OSError:
                logging.getLogger(__name__).warning(
                    "rephrase overlay save failed session=%s message_id=%s",
                    session_id,
                    message_id,
                    exc_info=True,
                )
            self.loading = False
            self.error = ""
