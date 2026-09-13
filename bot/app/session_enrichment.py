"""Shared session snapshot helpers (extraction history, engagement, disposition)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.schemas import ChecklistItem, Evidence

EXTRACTION_SOURCES: tuple[str, ...] = ("pattern", "gliner", "safety_phrase", "llm")

# Top-level keys that hold the latest disposition snapshot. Never wipe these
# when a later turn is question-mode / empty.
DISPOSITION_SNAPSHOT_KEYS: tuple[str, ...] = (
    "matched_factors",
    "candidate_conditions",
    "traversed_chunk_ids",
    "factor_matching_audit",
    "agent_trace",
    "graph_traversal",
)

# Question-turn graph payload. Empty incoming values must not wipe a prior slice.
INTAKE_SNAPSHOT_KEYS: tuple[str, ...] = ("intake_traversal",)

PRESERVE_IF_EMPTY_KEYS: tuple[str, ...] = DISPOSITION_SNAPSHOT_KEYS + INTAKE_SNAPSHOT_KEYS


def exposed_chat_graph_fields(
    state: dict[str, Any],
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Participant-facing graph payloads. Hidden on question turns."""
    if bool(state.get("question_mode")):
        return None, None
    graph = state.get("graph_traversal")
    intake = state.get("intake_traversal")
    return (
        graph if isinstance(graph, dict) else None,
        intake if isinstance(intake, dict) else None,
    )


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _item_key(d: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(d.get("text", "")),
        str(d.get("kind", "")),
        str(d.get("source", "")),
        str(d.get("label", "")),
    )


def checklist_item_dict(item: ChecklistItem | dict[str, Any]) -> dict[str, Any]:
    if isinstance(item, ChecklistItem):
        return item.model_dump()
    out: dict[str, Any] = {
        "text": str(item.get("text", "")),
        "kind": str(item.get("kind", "")),
        "source": str(item.get("source", "")),
        "label": str(item.get("label", "")),
    }
    raw_id = str(item.get("id") or "").strip()
    if raw_id:
        out["id"] = raw_id
    if "confirmed" in item:
        confirmed = item.get("confirmed")
        if isinstance(confirmed, bool):
            out["confirmed"] = confirmed
        elif isinstance(confirmed, str):
            out["confirmed"] = confirmed.strip().casefold() in {"true", "1", "yes"}
        else:
            out["confirmed"] = bool(confirmed)
    return out


def split_checklist_by_source(
    items: list[ChecklistItem] | list[dict[str, str]],
) -> dict[str, list[dict[str, str]]]:
    """Group checklist rows by extractor source (pattern / gliner / safety_phrase)."""
    grouped: dict[str, list[dict[str, str]]] = {src: [] for src in EXTRACTION_SOURCES}
    for raw in items:
        row = checklist_item_dict(raw)
        src = row.get("source", "")
        if src not in grouped:
            grouped[src] = []
        grouped[src].append(row)
    return grouped


def new_items_added(
    prior: list[dict[str, str]],
    merged: list[dict[str, str]],
) -> list[dict[str, str]]:
    seen = {_item_key(i) for i in prior}
    return [dict(x) for x in merged if _item_key(x) not in seen]


def build_turn_extraction_record(
    *,
    turn_index: int,
    user_message: str,
    turn_items: list[ChecklistItem] | list[dict[str, str]],
    prior_checklist: list[dict[str, str]],
    merged_checklist: list[dict[str, str]],
    timestamp: str | None = None,
    llm_enrichment: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Per-turn extraction snapshot.

    Cumulative checklist lives only at the session top level
    (``clinical_checklist``). Each history row keeps ``new_items`` + ``by_source``
    so the session checklist can be reconstructed turn-by-turn without tripling
    the full list inside extraction / graph payloads.
    """
    by_source = split_checklist_by_source(turn_items)
    if llm_enrichment:
        by_source.setdefault("llm", [])
        for row in llm_enrichment.get("applied") or []:
            item = checklist_item_dict(row)
            if item not in by_source["llm"]:
                by_source["llm"].append(item)
        for change in llm_enrichment.get("modified") or []:
            after = change.get("after") if isinstance(change, dict) else None
            if after:
                item = checklist_item_dict(after)
                if item not in by_source["llm"]:
                    by_source["llm"].append(item)
    record: dict[str, Any] = {
        "turn_index": turn_index,
        "timestamp": timestamp or _now_iso(),
        "user_message": user_message,
        "by_source": by_source,
        "new_items": new_items_added(prior_checklist, merged_checklist),
    }
    if llm_enrichment:
        record["llm_enrichment"] = llm_enrichment
    return record


def append_turn_extraction(
    history: list[dict[str, Any]] | None,
    turn_record: dict[str, Any],
) -> list[dict[str, Any]]:
    out = list(history or [])
    out.append(turn_record)
    return out


def default_engagement() -> dict[str, Any]:
    return {
        "turns": [],
        "total_user_words": 0,
        "total_user_chars": 0,
        "mean_round_trip_ms": 0.0,
        "median_round_trip_ms": 0.0,
        "session_duration_sec": 0.0,
        "feedback_up_count": 0,
        "feedback_down_count": 0,
    }


def _word_char_counts(text: str) -> tuple[int, int]:
    words = [w for w in text.split() if w.strip()]
    return len(words), len(text)


def engagement_from_messages(
    messages: list[dict[str, str]],
    *,
    existing: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Server-side engagement rollup from flat user/assistant transcript."""
    prior = dict(existing or default_engagement())
    engagement = dict(prior)
    turns: list[dict[str, Any]] = []
    turn_index = 0
    for msg in messages:
        if msg.get("role") != "user":
            continue
        turn_index += 1
        content = str(msg.get("content") or "")
        words, chars = _word_char_counts(content)
        turns.append(
            {
                "turn_index": turn_index,
                "timestamp": msg.get("timestamp") or _now_iso(),
                "user_word_count": words,
                "user_char_count": chars,
                "composer_to_send_ms": 0.0,
                "round_trip_ms": 0.0,
                "idle_before_turn_sec": 0.0,
            }
        )
    # Prefer richer study-app turn timing when lengths still match.
    prior_turns = prior.get("turns") or []
    if isinstance(prior_turns, list) and len(prior_turns) == len(turns):
        for i, turn in enumerate(turns):
            prev = prior_turns[i] if isinstance(prior_turns[i], dict) else {}
            for key in (
                "composer_to_send_ms",
                "round_trip_ms",
                "idle_before_turn_sec",
                "timestamp",
            ):
                if prev.get(key) not in (None, "", 0, 0.0):
                    turn[key] = prev[key]
    engagement["turns"] = turns
    engagement["total_user_words"] = sum(t["user_word_count"] for t in turns)
    engagement["total_user_chars"] = sum(t["user_char_count"] for t in turns)

    up = down = 0
    for msg in messages:
        if msg.get("role") != "assistant":
            continue
        fb = msg.get("feedback") if isinstance(msg, dict) else None
        rating = fb.get("rating") if isinstance(fb, dict) else None
        if rating == "up":
            up += 1
        elif rating == "down":
            down += 1
    engagement["feedback_up_count"] = up
    engagement["feedback_down_count"] = down

    for key in (
        "mean_round_trip_ms",
        "median_round_trip_ms",
        "session_duration_sec",
    ):
        if prior.get(key) not in (None, ""):
            engagement[key] = prior[key]
    return engagement


def slim_coverage(coverage: dict[str, Any] | None) -> dict[str, Any] | None:
    """Compact coverage report for session JSON (drop checklist key tuples)."""
    if not coverage:
        return None
    instances = []
    for inst in coverage.get("symptom_instances") or []:
        if not isinstance(inst, dict):
            continue
        instances.append(
            {
                "symptom_id": inst.get("symptom_id"),
                "display_name": inst.get("display_name"),
            }
        )
    return {
        "session_complete": bool(coverage.get("session_complete")),
        "symptoms_complete": bool(coverage.get("symptoms_complete")),
        "ready_for_disposition": bool(coverage.get("ready_for_disposition")),
        "missing_slots": list(coverage.get("missing_slots") or []),
        "active_symptom_id": coverage.get("active_symptom_id"),
        "symptom_instances": instances,
    }


def build_orchestrator_snapshot(state: dict[str, Any], *, turn_index: int) -> dict[str, Any]:
    """Orchestrator outcome fields for the current turn (always logged)."""
    coverage = state.get("coverage") or {}
    return {
        "turn_index": turn_index,
        "timestamp": _now_iso(),
        "risk_hits": list(state.get("risk_hits") or []),
        "escalated": bool(state.get("escalated")),
        "safety_reason": state.get("safety_reason"),
        "question_mode": bool(state.get("question_mode")),
        "questions_asked": int(state.get("questions_asked") or 0),
        "question_reason": state.get("question_reason"),
        "slot_being_asked": state.get("slot_being_asked"),
        "asked_factor": state.get("asked_factor"),
        "last_rank_topic": state.get("last_rank_topic"),
        "last_rank_tier": state.get("last_rank_tier"),
        "coverage_ready": bool(coverage.get("ready_for_disposition")),
        "coverage": slim_coverage(coverage if isinstance(coverage, dict) else None),
        "generator_failed": bool(state.get("generator_failed")),
        "comorbidities_acknowledged": bool(state.get("comorbidities_acknowledged")),
        "factor_states": dict(state.get("factor_states") or {}),
        "intake_traversal": compact_graph_for_session(
            state.get("intake_traversal") if isinstance(state.get("intake_traversal"), dict) else None
        )
        if bool(state.get("question_mode"))
        else None,
    }


def slim_factor_matching_audit(audit: dict[str, Any] | None) -> dict[str, Any] | None:
    """Keep summary + items + gaps; drop matched/unmatched partitions."""
    if not audit:
        return None
    return {
        "summary": audit.get("summary") or {},
        "items": list(audit.get("items") or []),
        "gaps": list(audit.get("gaps") or []),
    }


def compact_graph_for_session(graph_payload: dict[str, Any] | None) -> dict[str, Any] | None:
    """Strip fields stored once elsewhere in the disposition record."""
    if not graph_payload:
        return None
    out = dict(graph_payload)
    for key in (
        "checklist_items",
        "matched_factors",
        "candidate_conditions",
        "factor_matching",
        "agent_trace",
    ):
        out.pop(key, None)
    return out


def _evidence_rows(evidence: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in evidence or []:
        if isinstance(item, Evidence):
            rows.append(item.model_dump())
        elif isinstance(item, dict):
            rows.append(dict(item))
    return rows


def build_disposition_record(
    state: dict[str, Any],
    *,
    turn_index: int,
) -> dict[str, Any] | None:
    """Append-only disposition artifact when this turn left question mode.

    Factor / condition lists and audits are stored once here (not also nested
    under ``graph_traversal``).
    """
    if bool(state.get("question_mode")):
        return None

    graph = state.get("graph_traversal")
    matched = list(state.get("matched_factors") or [])
    conditions = list(state.get("candidate_conditions") or [])
    chunks = list(state.get("traversed_chunk_ids") or [])
    audit = slim_factor_matching_audit(state.get("factor_matching_audit"))
    agent = state.get("agent_trace")
    evidence = _evidence_rows(state.get("evidence"))

    # Risk-escalation / policy turns still count as disposition even without graph.
    if not any((graph, matched, conditions, chunks, audit, agent, evidence, state.get("escalated"))):
        # Non-question path with empty retrieval (e.g. GraphRAG off) — still log.
        if not (state.get("final_response") or state.get("draft_response")):
            return None

    return {
        "turn_index": turn_index,
        "timestamp": _now_iso(),
        "matched_factors": matched,
        "candidate_conditions": conditions,
        "traversed_chunk_ids": chunks,
        "factor_matching_audit": audit,
        "agent_trace": agent,
        "disposition_brief": state.get("disposition_brief"),
        "graph_traversal": compact_graph_for_session(graph if isinstance(graph, dict) else None),
        "intake_traversal": compact_graph_for_session(
            state.get("intake_traversal") if isinstance(state.get("intake_traversal"), dict) else None
        ),
        "evidence": evidence,
        "final_response": state.get("final_response"),
        "escalated": bool(state.get("escalated")),
        "safety_reason": state.get("safety_reason"),
        "risk_hits": list(state.get("risk_hits") or []),
    }


def build_intake_record(
    state: dict[str, Any],
    *,
    turn_index: int,
) -> dict[str, Any] | None:
    """Append-only planner slice when this turn asked a question."""
    if not bool(state.get("question_mode")):
        return None
    intake = state.get("intake_traversal")
    if not (intake or state.get("asked_factor") or state.get("question_reason")):
        return None
    return {
        "turn_index": turn_index,
        "timestamp": _now_iso(),
        "question_reason": state.get("question_reason"),
        "asked_factor": state.get("asked_factor"),
        "slot_being_asked": state.get("slot_being_asked"),
        "factor_states": dict(state.get("factor_states") or {}),
        "intake_traversal": compact_graph_for_session(
            intake if isinstance(intake, dict) else None
        ),
    }


def default_session_fields(session_id: str) -> dict[str, Any]:
    return {
        "session_id": session_id,
        "clinical_checklist": [],
        "messages": [],
        "extraction_history": [],
        "engagement": default_engagement(),
        "orchestrator": None,
        "orchestrator_history": [],
        "disposition_history": [],
        "intake_history": [],
        "matched_factors": [],
        "factor_states": {},
        "candidate_conditions": [],
        "traversed_chunk_ids": [],
        "factor_matching_audit": None,
        "agent_trace": None,
        "graph_traversal": None,
        "intake_traversal": None,
    }
