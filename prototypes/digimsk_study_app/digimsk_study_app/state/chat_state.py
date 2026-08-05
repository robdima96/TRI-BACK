"""Chat page state."""

from __future__ import annotations

from datetime import datetime, timezone

import reflex as rx

from digimsk_study_app.adapters.presentation import get_presentation_adapter
from digimsk_study_app.config import IDLE_TIMEOUT_SEC
from digimsk_study_app.models.chat_types import (
    ChatMessageItem,
    CitationItem,
    empty_message,
    normalize_citations,
)
from digimsk_study_app.session_store import load_session, save_session
from digimsk_study_app.state.auth_state import AuthState
from digimsk_study_app.state.engagement_tracker import (
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
            )
        )
    return out


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
        session = load_session(self.session_id)
        if not session:
            return
        self.messages = _session_messages_to_chat(session.get("messages"))
        self.turn_count = int(session.get("turn_count") or 0)
        self.escalated = bool(session.get("escalated"))
        self.safety_reason = str(session.get("safety_reason") or "")

    @rx.event
    def mount_chat(self):
        if not self._ensure_authenticated():
            return rx.redirect("/")
        self._load_chat_from_session()

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

            session_id = self.session_id
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
    async def rate_message(self, message_id: str, rating: str):
        if rating not in ("up", "down"):
            return
        if not self._ensure_authenticated():
            self.error = "Session expired. Please log in again."
            return

        updated: list[ChatMessageItem] = []
        for msg in self.messages:
            if msg["message_id"] == message_id and msg["role"] == "assistant":
                msg = {**msg, "feedback_rating": rating}
            updated.append(msg)
        self.messages = updated

        rated_at = _now_iso()
        # UI transcript is authoritative for study overlay (stable ids + ratings).
        messages = _messages_to_session(self.messages)
        for msg in messages:
            if msg.get("message_id") == message_id and msg.get("role") == "assistant":
                msg["feedback"] = {"rating": rating, "rated_at": rated_at}

        session = load_session(self.session_id) or {}
        up, down = feedback_tallies(messages)
        engagement = dict(session.get("engagement") or {})
        engagement["feedback_up_count"] = up
        engagement["feedback_down_count"] = down
        save_session(self.session_id, messages=messages, engagement=engagement)
