"""Shared session snapshot helpers (checklist extraction history, engagement)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.schemas import ChecklistItem

EXTRACTION_SOURCES: tuple[str, ...] = ("pattern", "gliner", "safety_phrase", "llm")


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _item_key(d: dict[str, str]) -> tuple[str, str, str, str]:
    return (
        d.get("text", ""),
        d.get("kind", ""),
        d.get("source", ""),
        d.get("label", ""),
    )


def checklist_item_dict(item: ChecklistItem | dict[str, str]) -> dict[str, str]:
    if isinstance(item, ChecklistItem):
        return item.model_dump()
    return {
        "text": str(item.get("text", "")),
        "kind": str(item.get("kind", "")),
        "source": str(item.get("source", "")),
        "label": str(item.get("label", "")),
    }


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
    """One per-turn extraction snapshot for session JSON."""
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
        "clinical_checklist": [dict(x) for x in merged_checklist],
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
    engagement = dict(existing or default_engagement())
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
    engagement["turns"] = turns
    engagement["total_user_words"] = sum(t["user_word_count"] for t in turns)
    engagement["total_user_chars"] = sum(t["user_char_count"] for t in turns)
    return engagement


def default_session_fields(session_id: str) -> dict[str, Any]:
    return {
        "session_id": session_id,
        "clinical_checklist": [],
        "messages": [],
        "extraction_history": [],
        "engagement": default_engagement(),
    }
