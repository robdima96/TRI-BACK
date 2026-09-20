"""One-shot rephrase of an intake assistant bubble (no graph invoke)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from langchain_core.messages import AIMessage, RemoveMessage

from app.session_store import load_session, save_session
from app.services.intake_llm import rephrase_assistant_text

_log = logging.getLogger(__name__)

_INTRO_MESSAGE_ID = "msg_intro"


@dataclass
class RephraseOutcome:
    status: str
    response: str = ""
    questions_asked: int = 0
    question_mode: bool = True

    @property
    def ok(self) -> bool:
        return self.status == "ok"


def _is_rephraseable(msg: dict[str, Any], *, last_assistant: bool, orch_question: bool) -> bool:
    if msg.get("role") != "assistant":
        return False
    if str(msg.get("message_id") or "") == _INTRO_MESSAGE_ID:
        return False
    if msg.get("question_mode") is False:
        return False
    if msg.get("question_mode") is True:
        return True
    return last_assistant and orch_question


def _patch_checkpoint_last_assistant(graph: Any, session_id: str, old: str, new: str) -> None:
    if graph is None or not old or old == new:
        return
    config = {"configurable": {"thread_id": session_id}}
    try:
        snapshot = graph.get_state(config)
        values = snapshot.values if snapshot is not None else {}
        messages = list(values.get("messages") or [])
    except Exception as exc:  # noqa: BLE001
        _log.info("rephrase checkpoint read failed session=%s: %s", session_id, exc)
        return
    for msg in reversed(messages):
        if not isinstance(msg, AIMessage):
            continue
        content = msg.content if isinstance(msg.content, str) else str(msg.content)
        if content.strip() != old.strip():
            continue
        mid = getattr(msg, "id", None)
        if not mid:
            return
        try:
            graph.update_state(
                config,
                {"messages": [RemoveMessage(id=mid), AIMessage(content=new, id=mid)]},
            )
        except Exception as exc:  # noqa: BLE001
            _log.info("rephrase checkpoint patch failed session=%s: %s", session_id, exc)
        return


def rephrase_session_message(
    *,
    session_id: str,
    message_id: str,
    graph: Any = None,
) -> RephraseOutcome:
    """Rewrite one assistant bubble in session JSON. Does not increment questions_asked."""
    sid = (session_id or "").strip()
    mid = (message_id or "").strip()
    if not sid or not mid:
        return RephraseOutcome(status="not_found")

    stored = load_session(sid)
    if not stored:
        return RephraseOutcome(status="not_found")

    messages = [dict(m) for m in (stored.get("messages") or []) if isinstance(m, dict)]
    orch = stored.get("orchestrator") if isinstance(stored.get("orchestrator"), dict) else {}
    questions_asked = int(orch.get("questions_asked") or 0)
    orch_question = bool(orch.get("question_mode"))

    last_assistant_idx = None
    for i in range(len(messages) - 1, -1, -1):
        if messages[i].get("role") == "assistant":
            last_assistant_idx = i
            break

    target_idx = None
    for i, msg in enumerate(messages):
        if str(msg.get("message_id") or "") == mid:
            target_idx = i
            break
    if target_idx is None:
        return RephraseOutcome(status="not_found", questions_asked=questions_asked)

    target = messages[target_idx]
    if target.get("rephrased"):
        return RephraseOutcome(
            status="already",
            response=str(target.get("content") or ""),
            questions_asked=questions_asked,
            question_mode=bool(target.get("question_mode", True)),
        )
    last_assistant = target_idx == last_assistant_idx
    if not _is_rephraseable(target, last_assistant=last_assistant, orch_question=orch_question):
        return RephraseOutcome(
            status="not_question",
            response=str(target.get("content") or ""),
            questions_asked=questions_asked,
            question_mode=False,
        )

    original = str(target.get("content") or "").strip()
    if not original:
        return RephraseOutcome(status="not_found", questions_asked=questions_asked)

    rewritten = rephrase_assistant_text(original)
    if not rewritten:
        return RephraseOutcome(
            status="unavailable",
            response=original,
            questions_asked=questions_asked,
        )

    messages[target_idx]["content"] = rewritten
    messages[target_idx]["rephrased"] = True
    save_session(sid, messages=messages)
    if last_assistant:
        _patch_checkpoint_last_assistant(graph, sid, original, rewritten)
    return RephraseOutcome(
        status="ok",
        response=rewritten,
        questions_asked=questions_asked,
        question_mode=True,
    )
