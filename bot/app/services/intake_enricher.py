"""LLM-backed checklist enrichment: propose additions, edits, and deletions."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Literal

from app.orchestrator.checklist import (
    ensure_checklist_ids,
    kind_family,
    new_checklist_id,
)
from app.orchestrator.coverage import coverage_intake_summary, evaluate_checklist_coverage
from app.orchestrator.intake_models import SlotName
from app.orchestrator.intake_slots import select_next_missing_slot
from app.schemas import ChecklistItem
from app.services.generator import generate_from_messages, generator_model_configured
from app.session_enrichment import checklist_item_dict

_log = logging.getLogger(__name__)

INTAKE_ENRICH_MAX_NEW_TOKENS = 4096

_JSON_FENCE_RE = re.compile(
    r"```(?:json)?\s*([\s\S]*?)\s*```",
    re.IGNORECASE,
)

_ALLOWED_KINDS: frozenset[str] = frozenset(
    {
        "demographic",
        "comorbidity",
        "duration",
        "severity",
        "symptom_quality",
        "provocative",
        "palliative",
        "ner_entity",
    }
)

_ALLOWED_NEXT_SLOTS: frozenset[str] = frozenset(
    {
        "age",
        "sex",
        "comorbidities",
        "symptom_anchor",
        "symptom_duration",
        "symptom_severity",
        "symptom_quality",
        "provocative",
        "palliative",
    }
)

_LABELS_BY_KIND: dict[str, frozenset[str]] = {
    "demographic": frozenset({"age", "sex"}),
    "comorbidity": frozenset({"comorbidity"}),
    "duration": frozenset({"duration"}),
    "severity": frozenset({"symptom_severity"}),
    "symptom_quality": frozenset({"symptom_quality"}),
    "provocative": frozenset({"provocative"}),
    "palliative": frozenset({"palliative"}),
    "ner_entity": frozenset(
        {
            "symptom",
            "symptom duration",
            "symptom quality",
            "symptom severity",
            "symptom provocative factor",
            "symptom palliative factor",
            "body part",
            "sign",
        }
    ),
}

OpName = Literal["add", "modify", "delete"]


@dataclass
class ProposedChecklistRow:
    text: str
    kind: str
    label: str
    reason: str

    def to_checklist_item(self) -> ChecklistItem:
        return ChecklistItem(
            text=self.text,
            kind=self.kind,
            source="llm",
            label=self.label,
        )

    def to_log_dict(self) -> dict[str, str]:
        return {
            "text": self.text,
            "kind": self.kind,
            "label": self.label,
            "source": "llm",
            "reason": self.reason,
        }


@dataclass
class ChecklistOperation:
    op: OpName
    reason: str
    text: str = ""
    kind: str = ""
    label: str = ""
    # Stable checklist row id (modify / delete only)
    id: str | None = None

    def to_log_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"op": self.op, "reason": self.reason}
        if self.id is not None:
            out["id"] = self.id
        if self.op in ("add", "modify"):
            out["text"] = self.text
            out["kind"] = self.kind
            out["label"] = self.label
            out["source"] = "llm"
        return out


@dataclass
class IntakeEnrichmentResult:
    status: str
    summary_reason: str = ""
    proposed: list[ChecklistOperation] = field(default_factory=list)
    applied: list[ChecklistItem] = field(default_factory=list)
    modified: list[dict[str, Any]] = field(default_factory=list)
    deleted: list[dict[str, Any]] = field(default_factory=list)
    rejected: list[dict[str, Any]] = field(default_factory=list)
    resulting_checklist: list[dict[str, Any]] | None = None
    comorbidities_acknowledged: bool = False
    # Draft next intake question from the same LLM call (may be unused if the
    # deterministic planner picks a different slot after applying ops).
    next_question: str | None = None
    next_slot: SlotName | None = None
    # Set when the model proposes next_intake that skips a still-missing higher
    # priority gap after ops (does not invent checklist rows).
    consistency_warning: dict[str, Any] | None = None
    raw_response: str = ""

    @property
    def applied_items(self) -> list[ChecklistItem]:
        return list(self.applied)

    @property
    def checklist_changed(self) -> bool:
        return bool(self.applied or self.modified or self.deleted)

    def to_log_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "status": self.status,
            "summary_reason": self.summary_reason,
            "comorbidities_acknowledged": self.comorbidities_acknowledged,
            "next_question": self.next_question,
            "next_slot": self.next_slot,
            "proposed": [op.to_log_dict() for op in self.proposed],
            "applied": [checklist_item_dict(item) for item in self.applied],
            "modified": list(self.modified),
            "deleted": list(self.deleted),
            "rejected": list(self.rejected),
        }
        if self.consistency_warning:
            out["consistency_warning"] = dict(self.consistency_warning)
        return out


def _format_checklist_block(checklist: list[dict[str, Any]]) -> str:
    if not checklist:
        return "(empty)"
    lines: list[str] = []
    for i, row in enumerate(checklist, 1):
        confirmed = "yes" if row.get("confirmed") else "no"
        lines.append(
            f"  [{row.get('id', '')}] ({i}) text={row.get('text', '')!r} "
            f"kind={row.get('kind', '')!r} source={row.get('source', '')!r} "
            f"label={row.get('label', '')!r} confirmed={confirmed}"
        )
    return "\n".join(lines)


def _format_history_block(history: list[dict[str, str]]) -> str:
    if not history:
        return "(no prior turns)"
    lines: list[str] = []
    for turn in history[-12:]:
        role = turn.get("role", "user")
        content = str(turn.get("content", "")).strip()
        if content:
            lines.append(f"  {role}: {content}")
    return "\n".join(lines) if lines else "(no prior turns)"


def _coverage_gap_summary(
    *,
    checklist: list[dict[str, str]],
    comorbidities_acknowledged: bool,
    last_asked_slot: SlotName | None,
    latest_user_message: str,
) -> str:
    coverage, _, _ = evaluate_checklist_coverage(
        checklist=checklist,
        comorbidities_acknowledged=comorbidities_acknowledged,
        last_asked_slot=last_asked_slot,
        latest_user_message=latest_user_message,
    )
    return coverage_intake_summary(coverage)


def _apply_next_slot_consistency_guard(
    *,
    checklist: list[dict[str, str]],
    comorbidities_acknowledged: bool,
    last_asked_slot: SlotName | None,
    latest_user_message: str,
    next_slot: SlotName | None,
    next_question: str | None,
) -> tuple[SlotName | None, str | None, dict[str, Any] | None]:
    """
    If the model proposes next_intake that is not the planner's next missing slot
    after ops, clear the draft and return an audit warning. Never invents rows.
    """
    if not next_slot:
        return next_slot, next_question, None

    coverage, _, _ = evaluate_checklist_coverage(
        checklist=checklist,
        comorbidities_acknowledged=comorbidities_acknowledged,
        last_asked_slot=last_asked_slot,
        latest_user_message=latest_user_message,
    )
    authoritative_slot, _ = select_next_missing_slot(
        coverage, comorbidities_acknowledged=comorbidities_acknowledged
    )
    if authoritative_slot is None or next_slot == authoritative_slot:
        return next_slot, next_question, None

    missing = [
        (
            m["slot"]
            if "symptom_id" not in m
            else f"{m['slot']}@{m['symptom_id']}"
        )
        for m in (coverage.get("missing_slots") or [])
    ]
    warning = {
        "message": (
            f"next_slot={next_slot} while authoritative_next_slot="
            f"{authoritative_slot}; missing={missing}"
        ),
        "proposed_next_slot": next_slot,
        "proposed_next_question": next_question,
        "authoritative_next_slot": authoritative_slot,
        "missing_slots": missing,
    }
    return None, None, warning


def _extract_json_object(text: str) -> dict[str, Any] | None:
    cleaned = text.strip()
    if not cleaned:
        return None
    fence = _JSON_FENCE_RE.search(cleaned)
    if fence:
        cleaned = fence.group(1).strip()
    try:
        data = json.loads(cleaned)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        pass
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start >= 0 and end > start:
        try:
            data = json.loads(cleaned[start : end + 1])
            return data if isinstance(data, dict) else None
        except json.JSONDecodeError:
            return None
    return None


def _validate_row_fields(
    text: str,
    kind: str,
    label: str,
    reason: str,
) -> ProposedChecklistRow | None:
    text = text.strip()
    kind = kind.strip()
    label = label.strip()
    reason = reason.strip()
    if not text or len(text) > 240:
        return None
    if kind not in _ALLOWED_KINDS:
        return None
    allowed_labels = _LABELS_BY_KIND.get(kind)
    if allowed_labels is not None and label.casefold() not in {
        value.casefold() for value in allowed_labels
    }:
        return None
    if not reason:
        reason = "Inferred from conversation context."
    return ProposedChecklistRow(text=text, kind=kind, label=label, reason=reason)


def _validate_proposed_row(raw: Any) -> ProposedChecklistRow | None:
    """Public/test helper: validate a proposed add-style row dict."""
    if not isinstance(raw, dict):
        return None
    return _validate_row_fields(
        str(raw.get("text") or ""),
        str(raw.get("kind") or ""),
        str(raw.get("label") or ""),
        str(raw.get("reason") or ""),
    )


def _row_identity(row: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(row.get("text", "")).casefold(),
        str(row.get("kind", "")),
        str(row.get("label", "")).casefold(),
    )


def _parse_row_id(raw: Any) -> str | None:
    if raw is None or isinstance(raw, bool):
        return None
    value = str(raw).strip()
    return value or None


def _validate_operation(raw: Any) -> ChecklistOperation | None:
    if not isinstance(raw, dict):
        return None
    op = str(raw.get("op") or raw.get("action") or "").strip().casefold()
    if op in {"addition", "add_row", "create"}:
        op = "add"
    elif op in {"edit", "update", "replace", "correction"}:
        op = "modify"
    elif op in {"remove", "drop"}:
        op = "delete"
    if op not in {"add", "modify", "delete"}:
        return None
    reason = str(raw.get("reason") or "").strip() or "Inferred from conversation context."

    if op == "delete":
        row_id = _parse_row_id(raw.get("id"))
        if row_id is None:
            return None
        return ChecklistOperation(op="delete", reason=reason, id=row_id)

    row = _validate_row_fields(
        str(raw.get("text") or ""),
        str(raw.get("kind") or ""),
        str(raw.get("label") or ""),
        reason,
    )
    if row is None:
        return None

    if op == "add":
        return ChecklistOperation(
            op="add",
            reason=row.reason,
            text=row.text,
            kind=row.kind,
            label=row.label,
        )

    row_id = _parse_row_id(raw.get("id"))
    if row_id is None:
        return None
    return ChecklistOperation(
        op="modify",
        reason=row.reason,
        text=row.text,
        kind=row.kind,
        label=row.label,
        id=row_id,
    )


def _legacy_additions_as_ops(payload: dict[str, Any]) -> list[Any]:
    """Treat checklist_additions as add ops for backward compatibility."""
    out: list[dict[str, Any]] = []
    for raw in payload.get("checklist_additions") or []:
        if not isinstance(raw, dict):
            continue
        item = dict(raw)
        item.setdefault("op", "add")
        out.append(item)
    return out


def _collect_raw_operations(payload: dict[str, Any]) -> list[Any]:
    for key in ("checklist_operations", "checklist_changes", "operations"):
        raw_ops = payload.get(key)
        if isinstance(raw_ops, list) and raw_ops:
            return list(raw_ops)
    return _legacy_additions_as_ops(payload)


def apply_checklist_operations(
    checklist: list[dict[str, Any]],
    operations: list[ChecklistOperation],
) -> tuple[
    list[dict[str, Any]],
    list[ChecklistItem],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    """
    Apply validated ops against the starting checklist by stable row id.

    Ids always refer to the original checklist (stable across the batch).
    Delete wins over modify on the same id. Adds append after surviving rows
    and are deduped by (text, kind, label). Successful add/modify rows are
    marked ``confirmed=True``. Confirmed rows reject cross-family modifies.
    """
    starting = ensure_checklist_ids([dict(r) for r in checklist])
    by_id = {str(row["id"]): row for row in starting}
    delete_ids: set[str] = set()
    modify_by_id: dict[str, ChecklistOperation] = {}
    adds: list[ChecklistOperation] = []
    rejected: list[dict[str, Any]] = []

    for op in operations:
        if op.op == "add":
            adds.append(op)
            continue
        assert op.id is not None
        row_id = op.id
        if row_id not in by_id:
            rejected.append(
                {
                    **op.to_log_dict(),
                    "reject_reason": "unknown_id",
                }
            )
            continue
        if op.op == "delete":
            delete_ids.add(row_id)
            modify_by_id.pop(row_id, None)
            continue
        # modify
        if row_id in delete_ids:
            rejected.append(
                {
                    **op.to_log_dict(),
                    "reject_reason": "conflicting_delete_on_same_id",
                }
            )
            continue
        target = by_id[row_id]
        if bool(target.get("confirmed")) and kind_family(
            str(target.get("kind", "")), str(target.get("label", ""))
        ) != kind_family(op.kind, op.label):
            rejected.append(
                {
                    **op.to_log_dict(),
                    "reject_reason": "kind_family_mismatch",
                }
            )
            continue
        modify_by_id[row_id] = op

    applied: list[ChecklistItem] = []
    modified: list[dict[str, Any]] = []
    deleted: list[dict[str, Any]] = []
    resulting: list[dict[str, Any]] = []
    seen = set()

    for row in starting:
        row_id = str(row["id"])
        if row_id in delete_ids:
            deleted.append(
                {
                    "id": row_id,
                    "before": checklist_item_dict(row),
                    "reason": next(
                        (
                            op.reason
                            for op in operations
                            if op.op == "delete" and op.id == row_id
                        ),
                        "Removed based on conversation context.",
                    ),
                }
            )
            continue
        if row_id in modify_by_id:
            op = modify_by_id[row_id]
            new_row: dict[str, Any] = {
                "id": row_id,
                "text": op.text,
                "kind": op.kind,
                "source": "llm",
                "label": op.label,
                "confirmed": True,
            }
            key = _row_identity(new_row)
            if key in seen:
                rejected.append(
                    {
                        **op.to_log_dict(),
                        "reject_reason": "duplicate_of_existing_checklist_row",
                    }
                )
                # Keep the original row if the replacement would duplicate.
                key_orig = _row_identity(row)
                if key_orig not in seen:
                    seen.add(key_orig)
                    resulting.append(dict(row))
                continue
            if key == _row_identity(row) and new_row["text"] == row.get("text"):
                # No material change to text/kind/label; still confirm if enrichment
                # re-accepted the same fact.
                kept = dict(row)
                kept["confirmed"] = True
                key_orig = _row_identity(kept)
                if key_orig not in seen:
                    seen.add(key_orig)
                    resulting.append(kept)
                if not row.get("confirmed"):
                    modified.append(
                        {
                            "id": row_id,
                            "before": checklist_item_dict(row),
                            "after": checklist_item_dict(kept),
                            "reason": op.reason,
                        }
                    )
                else:
                    rejected.append(
                        {
                            **op.to_log_dict(),
                            "reject_reason": "no_material_change",
                        }
                    )
                continue
            seen.add(key)
            resulting.append(new_row)
            modified.append(
                {
                    "id": row_id,
                    "before": checklist_item_dict(row),
                    "after": dict(new_row),
                    "reason": op.reason,
                }
            )
            continue
        key = _row_identity(row)
        if key in seen:
            # Collapse accidental duplicates already present; keep first.
            continue
        seen.add(key)
        resulting.append(dict(row))

    for op in adds:
        row_id = new_checklist_id()
        item = ChecklistItem(
            text=op.text,
            kind=op.kind,
            source="llm",
            label=op.label,
            id=row_id,
            confirmed=True,
        )
        key = _row_identity(item.model_dump())
        if key in seen:
            rejected.append(
                {
                    **op.to_log_dict(),
                    "reject_reason": "duplicate_of_existing_checklist_row",
                }
            )
            continue
        seen.add(key)
        resulting.append(item.model_dump())
        applied.append(item)

    return resulting, applied, modified, deleted, rejected


def _parse_next_intake(
    payload: dict[str, Any],
) -> tuple[str | None, SlotName | None]:
    """Extract an optional next intake question from the combined LLM payload."""
    raw = payload.get("next_intake")
    if raw is None:
        # Flat fallback if the model omitted the nested object.
        question = str(payload.get("next_question") or "").strip()
        slot_raw = str(payload.get("next_slot") or "").strip().casefold()
    elif isinstance(raw, dict):
        question = str(raw.get("question") or raw.get("next_question") or "").strip()
        slot_raw = str(raw.get("slot") or raw.get("next_slot") or "").strip().casefold()
    else:
        return None, None

    if not question or slot_raw not in _ALLOWED_NEXT_SLOTS:
        return None, None
    return question, slot_raw  # type: ignore[return-value]


def _build_enrichment_messages(
    *,
    checklist: list[dict[str, Any]],
    conversation_history: list[dict[str, str]],
    latest_user_message: str,
    last_asked_slot: SlotName | None,
    comorbidities_acknowledged: bool,
) -> list[dict[str, str]]:
    slot_hint = last_asked_slot or "(none)"
    gap_summary = _coverage_gap_summary(
        checklist=checklist,
        comorbidities_acknowledged=comorbidities_acknowledged,
        last_asked_slot=last_asked_slot,
        latest_user_message=latest_user_message,
    )
    instruction = (
        "You are a careful overseer of a structured clinical intake checklist for a "
        "musculoskeletal triage chatbot.\n\n"
        "In ONE response you must (1) maintain the checklist and (2) draft the next "
        "intake question if coverage will still be incomplete after your updates.\n\n"
        "Read the transcript, existing checklist, coverage gaps, and the latest patient "
        "message. Maintain the checklist so it stays accurate and cumulative: add missing "
        "facts, correct rows that are wrong or outdated, and delete rows that the patient "
        "clearly retracted or that were recorded in error.\n\n"
        "Volunteered facts (critical):\n"
        "- Last intake slot asked is a HINT about what the assistant was seeking, NOT a "
        "limit on what you may add or edit.\n"
        "- Pattern extractors and GliNER often miss or mislabel facts. If the patient "
        "clearly stated something clinically relevant and it is not already on the "
        "checklist with the correct kind/label, you MUST add or modify a row for it in "
        "this turn—deleting bad extractor rows alone is not enough.\n"
        "- You may fill ANY still-missing slot from the latest message or transcript "
        "(duration, quality, severity, provocative, palliative, comorbidities, etc.), "
        "even when that slot was not the one just asked.\n"
        "- Prefer typed kinds that satisfy coverage: duration, severity, "
        "symptom_quality, provocative, palliative (rather than only ner_entity aliases) "
        "when the fact fills an intake slot.\n"
        "- Consistency: if summary_reason says the patient provided a fact (e.g. a "
        "provocative factor), checklist_operations MUST include a matching add or "
        "modify. Do not set next_intake.slot past a gap you claim is filled unless an "
        "operation actually fills that gap.\n"
        "- Example: assistant asked about pain quality; patient says "
        "'It's a dull ache ... and it's hard to sit in my chair at work'. "
        "Add dull/ache as symptom_quality if needed; ALSO add sitting (or "
        "'hard to sit') as kind=provocative, label=provocative; delete mislabeled "
        "body-part rows like 'chair'/'work' if present; only then may next_intake "
        "advance to palliative if provocative is covered.\n\n"
        "Important rules for checklist_operations:\n"
        "- Prefer evidence already stated by the patient; do not invent medications, "
        "diagnoses, or unrelated conditions.\n"
        "- Address modify/delete by the stable row id in brackets (e.g. cl_a1b2c3d4e5f6). "
        "Do NOT use numeric indexes to target rows.\n"
        "- New comorbidities, medications, or unrelated conditions → always use add. "
        "Never modify an existing row into a different clinical topic "
        "(e.g. do not overwrite a fall/trauma provocative row with a medication).\n"
        "- modify only to refine the SAME fact: wording, specificity, or a better "
        "allowed kind/label for that same finding (e.g. refine severity text, upgrade "
        "'fall' to 'fell from a ladder' while staying provocative).\n"
        "- Rows marked confirmed=yes were already accepted; do not silently overwrite "
        "them with a different kind of fact—add a new row instead.\n"
        "- If the assistant asked for confirmation (e.g. chief complaint) and the "
        "patient answered yes/affirmed, add the chief complaint as a symptom row.\n"
        "- If the patient restated their main symptom, add or correct it as "
        "kind=ner_entity, label=symptom.\n"
        "- Delete only when clearly unsupported now (explicit correction, clear "
        "negation of that fact, or obvious extractor error). Do not delete uncertain "
        "rows. Do not delete trauma/mechanism rows unless the patient explicitly "
        "denied them.\n"
        "- Do not duplicate facts already present after your changes.\n"
        "- Each operation needs a short reason string.\n\n"
        "Allowed kinds and labels:\n"
        "- demographic: age | sex\n"
        "- comorbidity: comorbidity\n"
        "- duration: duration\n"
        "- severity: symptom_severity\n"
        "- symptom_quality: symptom_quality\n"
        "- provocative: provocative\n"
        "- palliative: palliative\n"
        "- ner_entity: symptom | symptom duration | symptom quality | symptom severity | "
        "symptom provocative factor | symptom palliative factor | body part | sign\n\n"
        "Rules for next_intake (the follow-up question):\n"
        "- After imagining your checklist_operations applied, pick the single highest-"
        "priority still-missing slot and write ONE plain question for it.\n"
        "- Slot priority order: age → sex → symptom_anchor → symptom_quality → "
        "symptom_severity → symptom_duration → provocative → palliative → "
        "comorbidities.\n"
        "- Allowed slot values: age | sex | comorbidities | symptom_anchor | "
        "symptom_duration | symptom_severity | symptom_quality | provocative | "
        "palliative.\n"
        "- Output exactly one complete question sentence ending with ?.\n"
        "- Stay on that slot's topic; do not ask about medications unless the slot is "
        "comorbidities.\n"
        "- Do not give triage advice or a diagnosis.\n"
        "- If coverage would be complete after your updates (ready for disposition), "
        "set next_intake to null.\n\n"
        f"Last intake slot asked by assistant: {slot_hint}\n"
        f"Coverage before enrichment:\n{gap_summary}\n\n"
        f"Existing checklist (modify/delete by id in brackets; numbers are display-only):\n"
        f"{_format_checklist_block(checklist)}\n\n"
        f"Conversation transcript:\n{_format_history_block(conversation_history)}\n"
        f"Latest patient message: {latest_user_message.strip() or '(none)'}\n\n"
        "Return JSON only with this shape:\n"
        "{\n"
        '  "summary_reason": "one sentence explaining your updates or why none",\n'
        '  "comorbidities_acknowledged": false,\n'
        '  "checklist_operations": [\n'
        '    {"op": "add", "text": "...", "kind": "...", "label": "...", "reason": "..."},\n'
        '    {"op": "modify", "id": "cl_...", "text": "...", "kind": "...", "label": "...", '
        '"reason": "..."},\n'
        '    {"op": "delete", "id": "cl_...", "reason": "..."}\n'
        "  ],\n"
        '  "next_intake": {"slot": "age", "question": "How old are you?"}\n'
        "}\n"
        "Use an empty checklist_operations list when no changes are needed.\n"
        "Set comorbidities_acknowledged to true only when the patient clearly denies "
        "other health conditions after being asked (e.g. none / no conditions).\n"
        "Set next_intake to null when no further intake question is needed."
    )
    messages: list[dict[str, str]] = []
    for turn in conversation_history:
        role = turn.get("role", "user")
        if role not in ("user", "assistant"):
            role = "user"
        messages.append({"role": role, "content": turn.get("content", "")})
    messages.append({"role": "user", "content": instruction})
    return messages


def propose_checklist_enrichment(
    *,
    checklist: list[dict[str, Any]],
    conversation_history: list[dict[str, str]],
    latest_user_message: str,
    last_asked_slot: SlotName | None = None,
    comorbidities_acknowledged: bool = False,
    session_id: str = "",
    turn_index: int = 0,
) -> IntakeEnrichmentResult:
    """
    Ask the generator LLM to oversee checklist rows (add / modify / delete)
    and draft the next intake question in the same call.

    ``evaluate_checklist_coverage`` remains authoritative for which slot is
    asked; the drafted question is only used when it matches the planner's
    chosen slot. Mutations still pass kind/label/id filters before merge.
    """
    checklist = ensure_checklist_ids([dict(r) for r in checklist])

    if not generator_model_configured():
        return IntakeEnrichmentResult(
            status="unavailable",
            summary_reason="Generator LLM not configured; skipped checklist enrichment.",
        )

    try:
        messages = _build_enrichment_messages(
            checklist=checklist,
            conversation_history=conversation_history,
            latest_user_message=latest_user_message,
            last_asked_slot=last_asked_slot,
            comorbidities_acknowledged=comorbidities_acknowledged,
        )
        raw = generate_from_messages(
            messages,
            max_new_tokens=INTAKE_ENRICH_MAX_NEW_TOKENS,
            temperature=0.15,
        )
    except Exception as exc:
        _log.exception("intake enrichment LLM failed session=%s: %s", session_id, exc)
        return IntakeEnrichmentResult(
            status="error",
            summary_reason=f"LLM enrichment failed: {exc}",
        )

    payload = _extract_json_object(raw)
    if not payload:
        _log.info(
            "intake enrichment parse failed session=%s turn=%s raw=%r",
            session_id,
            turn_index,
            raw[:200],
        )
        return IntakeEnrichmentResult(
            status="parse_error",
            summary_reason="Could not parse LLM enrichment JSON.",
            raw_response=raw[:2000],
        )

    summary = str(payload.get("summary_reason") or "").strip()
    # Only the JSON boolean ``true`` counts; strings like "false"/"no" must not
    # sticky-ack comorbidities (Python ``bool("false")`` is True).
    ack = payload.get("comorbidities_acknowledged") is True
    next_question, next_slot = _parse_next_intake(payload)
    raw_ops = _collect_raw_operations(payload)
    proposed: list[ChecklistOperation] = []
    invalid_count = 0
    for raw_op in raw_ops:
        op = _validate_operation(raw_op)
        if op is not None:
            proposed.append(op)
        else:
            invalid_count += 1

    resulting, applied, modified, deleted, rejected = apply_checklist_operations(
        checklist, proposed
    )

    changed = bool(applied or modified or deleted)
    status = "applied" if changed or ack else "no_changes"
    if proposed and not changed and not ack:
        status = "rejected_all"

    post_checklist = resulting if changed else list(checklist)
    post_ack = bool(comorbidities_acknowledged or ack)
    next_slot, next_question, consistency_warning = _apply_next_slot_consistency_guard(
        checklist=post_checklist,
        comorbidities_acknowledged=post_ack,
        last_asked_slot=last_asked_slot,
        latest_user_message=latest_user_message,
        next_slot=next_slot,
        next_question=next_question,
    )
    if consistency_warning:
        _log.info(
            "intake_enrichment consistency_warning session=%s turn=%s %s",
            session_id,
            turn_index,
            consistency_warning.get("message"),
        )

    result = IntakeEnrichmentResult(
        status=status,
        summary_reason=summary or "LLM enrichment completed.",
        proposed=proposed,
        applied=applied,
        modified=modified,
        deleted=deleted,
        rejected=rejected,
        resulting_checklist=resulting if changed else None,
        comorbidities_acknowledged=ack,
        next_question=next_question,
        next_slot=next_slot,
        consistency_warning=consistency_warning,
        raw_response=raw[:2000],
    )
    _log.info(
        "intake_enrichment session=%s turn=%s status=%s reason=%r proposed=%d "
        "added=%d modified=%d deleted=%d rejected=%d invalid=%d ack=%s "
        "next_slot=%s consistency_warning=%s",
        session_id,
        turn_index,
        result.status,
        result.summary_reason,
        len(proposed),
        len(applied),
        len(modified),
        len(deleted),
        len(rejected),
        invalid_count,
        ack,
        next_slot,
        bool(consistency_warning),
    )
    return result
