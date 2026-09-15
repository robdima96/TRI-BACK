"""Restore LangGraph thread state from durable session JSON when /tmp SQLite is empty."""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage

from app.orchestrator.dormant import DORMANT_PHASE, INTAKE_PHASE
from app.session_store import load_session

_log = logging.getLogger(__name__)

_INTRO_MESSAGE_ID = "msg_intro"


def _lc_messages_from_session(raw: list[Any] | None) -> list[HumanMessage | AIMessage]:
    out: list[HumanMessage | AIMessage] = []
    for row in raw or []:
        if not isinstance(row, dict):
            continue
        if str(row.get("message_id") or "") == _INTRO_MESSAGE_ID:
            continue
        role = row.get("role")
        content = row.get("content")
        if not isinstance(content, str) or not content:
            continue
        if role == "user":
            out.append(HumanMessage(content=content))
        elif role == "assistant":
            out.append(AIMessage(content=content))
    return out


def resume_values_from_session(stored: dict[str, Any]) -> dict[str, Any]:
    """Build a ChatState patch from a session snapshot (no incoming user turn)."""
    orch = stored.get("orchestrator") or {}
    if not isinstance(orch, dict):
        orch = {}
    history = stored.get("orchestrator_history") or []
    if isinstance(history, list) and history:
        last = history[-1]
        if isinstance(last, dict):
            orch = {**orch, **last}

    phase = stored.get("session_phase") or orch.get("session_phase")
    if not phase:
        if stored.get("disposition_history") or orch.get("coverage_ready"):
            phase = DORMANT_PHASE
        else:
            phase = INTAKE_PHASE

    values: dict[str, Any] = {
        "session_id": stored.get("session_id") or "",
        "clinical_checklist": list(stored.get("clinical_checklist") or []),
        "extraction_history": list(stored.get("extraction_history") or []),
        "factor_states": dict(stored.get("factor_states") or orch.get("factor_states") or {}),
        "comorbidities_acknowledged": bool(
            stored.get("comorbidities_acknowledged")
            if stored.get("comorbidities_acknowledged") is not None
            else orch.get("comorbidities_acknowledged")
        ),
        "questions_asked": int(orch.get("questions_asked") or 0),
        "last_asked_slot": orch.get("slot_being_asked") or orch.get("last_asked_slot"),
        "last_rank_topic": orch.get("last_rank_topic"),
        "last_rank_tier": orch.get("last_rank_tier"),
        "session_phase": phase,
        "coverage": orch.get("coverage") if isinstance(orch.get("coverage"), dict) else {},
    }
    messages = _lc_messages_from_session(stored.get("messages"))
    if messages:
        values["messages"] = messages
    return values


def checkpoint_missing_checklist(values: dict[str, Any] | None) -> bool:
    if not values:
        return True
    return not bool(values.get("clinical_checklist"))


def maybe_resume_from_session(graph: Any, config: dict[str, Any], session_id: str) -> None:
    """If the checkpointer has no checklist, restore durable session JSON into the thread."""
    stored = load_session(session_id)
    if not stored or not (stored.get("clinical_checklist") or stored.get("session_phase")):
        return
    try:
        snapshot = graph.get_state(config)
        values = snapshot.values if snapshot is not None else {}
    except Exception as exc:  # noqa: BLE001 — missing thread is the resume case
        _log.info("checkpoint get_state failed for %s (%s); resuming from session JSON", session_id, exc)
        values = {}
    if not checkpoint_missing_checklist(values) and values.get("session_phase"):
        return
    patch = resume_values_from_session(stored)
    if not patch.get("clinical_checklist") and not patch.get("session_phase"):
        return
    graph.update_state(config, patch)
    _log.info("restored session %s from durable JSON into LangGraph checkpoint", session_id)
