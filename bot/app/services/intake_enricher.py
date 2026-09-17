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
from app.orchestrator.slot_answers import (
    canonicalize_floor_slot_text,
    is_na_slot_text,
)
from app.schemas import ChecklistItem
from app.triage_profiles import TriageProfile, get_triage_profile
from app.services.generator import generate_from_messages, generator_model_configured
from app.services.rag.factor_polarity import (
    ASKED_FACTOR_NOT_ANSWERED,
    FACTOR_STATE_AFFIRMED,
    FACTOR_STATE_DENIED,
    FACTOR_STATE_UNKNOWN,
)
from app.session_enrichment import checklist_item_dict

_log = logging.getLogger(__name__)

INTAKE_ENRICH_MAX_NEW_TOKENS = 4096

# Gemini 3.x ignores low temperature; mime+schema replaces that determinism lever.
ENRICHMENT_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "OBJECT",
    "properties": {
        "summary_reason": {"type": "STRING"},
        "comorbidities_acknowledged": {"type": "BOOLEAN"},
        "checklist_operations": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "op": {"type": "STRING"},
                    "id": {"type": "STRING"},
                    "text": {"type": "STRING"},
                    "kind": {"type": "STRING"},
                    "label": {"type": "STRING"},
                    "reason": {"type": "STRING"},
                },
                "required": ["op", "reason"],
            },
        },
        "next_intake": {
            "type": "OBJECT",
            "nullable": True,
            "properties": {
                "slot": {"type": "STRING"},
                "question": {"type": "STRING"},
            },
        },
        "asked_factor_reply": {
            "type": "STRING",
            "nullable": True,
        },
        "patient_answer": {
            "type": "STRING",
            "nullable": True,
        },
    },
    "required": ["summary_reason", "checklist_operations"],
}

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

_ALLOWED_POLARITIES: frozenset[str] = frozenset(
    {FACTOR_STATE_AFFIRMED, FACTOR_STATE_DENIED, FACTOR_STATE_UNKNOWN}
)
_ALLOWED_ASKED_FACTOR_REPLIES: frozenset[str] = frozenset(
    {
        FACTOR_STATE_AFFIRMED,
        FACTOR_STATE_DENIED,
        FACTOR_STATE_UNKNOWN,
        ASKED_FACTOR_NOT_ANSWERED,
    }
)
_ENRICHER_LLM_OK = frozenset({"applied", "no_changes", "rejected_all"})


@dataclass(frozen=True)
class FactorStateUpdate:
    """Ontology-gated Factor polarity from the intake enricher."""

    factor: str
    polarity: str
    reason: str = ""

    def to_log_dict(self) -> dict[str, str]:
        out = {"factor": self.factor, "polarity": self.polarity}
        if self.reason:
            out["reason"] = self.reason
        return out


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
    asked_factor_reply: str | None = None
    patient_answer: str | None = None
    # Set when the model proposes next_intake that skips a still-missing higher
    # priority gap after ops (does not invent checklist rows).
    consistency_warning: dict[str, Any] | None = None
    raw_response: str = ""

    @property
    def llm_ran(self) -> bool:
        """True when the generator returned parseable JSON."""
        return self.status in _ENRICHER_LLM_OK

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
            "asked_factor_reply": self.asked_factor_reply,
            "patient_answer": self.patient_answer,
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


def _coverage_gap_summary(
    *,
    checklist: list[dict[str, str]],
    comorbidities_acknowledged: bool,
    last_asked_slot: SlotName | None,
    latest_user_message: str,
    preferred_body_parts: tuple[str, ...] | None = None,
) -> str:
    coverage, _, _ = evaluate_checklist_coverage(
        checklist=checklist,
        comorbidities_acknowledged=comorbidities_acknowledged,
        last_asked_slot=last_asked_slot,
        latest_user_message=latest_user_message,
        preferred_body_parts=preferred_body_parts,
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
    preferred_body_parts: tuple[str, ...] | None = None,
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
        preferred_body_parts=preferred_body_parts,
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
            if is_na_slot_text(str(by_id[row_id].get("text") or "")):
                rejected.append(
                    {
                        **op.to_log_dict(),
                        "reject_reason": "na_slot_protected",
                    }
                )
                continue
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
                "text": canonicalize_floor_slot_text(op.kind, op.text),
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
            text=canonicalize_floor_slot_text(op.kind, op.text),
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


def _inventory_factor_names(profile: TriageProfile | None = None) -> tuple[str, ...]:
    """Canonical Factor names from the inventory JSON, with ontology fallback."""
    from app.services.rag.factor_patterns import load_factor_names
    from app.triage_profiles import load_ontology_for_profile

    pack = profile or get_triage_profile()
    names = load_factor_names(str(pack.graph_inventory))
    if names:
        return names
    try:
        return load_ontology_for_profile(pack).all_factors
    except Exception:
        return ()


def _canonical_inventory_factor(
    name: str, inventory: tuple[str, ...]
) -> str | None:
    key = (name or "").strip().casefold()
    if not key or not inventory:
        return None
    by_cf = {item.casefold(): item for item in inventory}
    return by_cf.get(key)


def parse_factor_matches(
    payload: dict[str, Any],
    *,
    inventory: tuple[str, ...],
) -> tuple[list[FactorStateUpdate], int]:
    """Return accepted updates and a count of dropped/invalid entries."""
    raw = payload.get("factor_matches")
    if raw is None:
        raw = payload.get("factor_updates")
    if not isinstance(raw, list):
        return [], 0
    accepted: list[FactorStateUpdate] = []
    rejected = 0
    seen: set[str] = set()
    for entry in raw:
        if not isinstance(entry, dict):
            rejected += 1
            continue
        canonical = _canonical_inventory_factor(
            str(entry.get("factor") or entry.get("factor_name") or ""),
            inventory,
        )
        polarity = str(entry.get("polarity") or "").strip().casefold()
        if canonical is None or polarity not in _ALLOWED_POLARITIES:
            rejected += 1
            continue
        if canonical in seen:
            # Later row for the same factor wins.
            accepted = [item for item in accepted if item.factor != canonical]
        seen.add(canonical)
        accepted.append(
            FactorStateUpdate(
                factor=canonical,
                polarity=polarity,
                reason=str(entry.get("reason") or "").strip(),
            )
        )
    return accepted, rejected


def apply_factor_state_updates(
    existing: dict[str, str] | None,
    updates: list[FactorStateUpdate],
) -> dict[str, str]:
    """Merge LLM Factor polarities. ``unknown`` does not clear a sticky state."""
    out = dict(existing or {})
    for upd in updates:
        if upd.polarity == FACTOR_STATE_UNKNOWN:
            out.setdefault(upd.factor, FACTOR_STATE_UNKNOWN)
        else:
            out[upd.factor] = upd.polarity
    return out


def _format_factor_states_block(factor_states: dict[str, str] | None) -> str:
    if not factor_states:
        return "(none yet)"
    lines: list[str] = []
    for name in sorted(factor_states):
        polarity = factor_states[name]
        if polarity not in _ALLOWED_POLARITIES:
            continue
        lines.append(f"  - {name}: {polarity}")
    return "\n".join(lines) if lines else "(none yet)"


def _format_inventory_block(inventory: tuple[str, ...]) -> str:
    if not inventory:
        return "(inventory unavailable)"
    return "\n".join(f"  - {name}" for name in inventory)


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


def _parse_asked_factor_reply(payload: dict[str, Any]) -> str | None:
    raw = payload.get("asked_factor_reply")
    if raw is None:
        return None
    value = str(raw).strip().casefold()
    if value in {"", "null", "none"}:
        return None
    if value in _ALLOWED_ASKED_FACTOR_REPLIES:
        return value
    return None


def _parse_patient_answer(payload: dict[str, Any]) -> str | None:
    raw = payload.get("patient_answer")
    if raw is None:
        return None
    value = str(raw).strip()
    if not value or value.casefold() in {"null", "none"}:
        return None
    return value


def _format_last_exchange_block(
    *,
    last_assistant_message: str,
    latest_user_message: str,
) -> str:
    lines: list[str] = []
    if last_assistant_message.strip():
        lines.append(f"  assistant: {last_assistant_message.strip()}")
    if latest_user_message.strip():
        lines.append(f"  user: {latest_user_message.strip()}")
    return "\n".join(lines) if lines else "(first patient turn — no prior assistant question)"


def _last_assistant_from_history(history: list[dict[str, str]]) -> str:
    for turn in reversed(history):
        if turn.get("role") == "assistant":
            return str(turn.get("content") or "").strip()
    return ""


def _next_intake_slot_rules(profile: TriageProfile | None) -> str:
    """Slot-priority hint for the combined intake LLM prompt."""
    assumed = (profile.symptom_text.strip() if profile and profile.assumes_symptom else "")
    if assumed:
        return (
            f"- The chief complaint is already assumed to be {assumed}. Do not ask "
            "what body area or main symptom is bothering them, and do not choose "
            "symptom_anchor as next_intake.slot.\n"
            "- Slot priority order: age → sex → comorbidities → "
            "symptom_quality → symptom_severity → provocative → palliative → "
            "symptom_duration.\n"
        )
    return (
        "- Slot priority order: symptom_anchor → age → sex → comorbidities → "
        "symptom_quality → symptom_severity → provocative → palliative → "
        "symptom_duration.\n"
    )


def _patient_answer_prompt_block(
    question_spans: list[str] | None,
    graph_packet: str | None,
) -> str:
    questions = [s.strip() for s in (question_spans or []) if s and s.strip()]
    if not questions:
        return (
            "Rules for patient_answer:\n"
            "- The patient did not ask a clarifying question. Set patient_answer to null.\n\n"
        )
    packet = (graph_packet or "").strip() or "(empty graph packet)"
    quoted = " ".join(questions)
    return (
        "Rules for patient_answer (the patient's clarifying question):\n"
        "- Write 1-3 sentences using ONLY the knowledge-graph packet below.\n"
        "- Never recommend the emergency department, urgent care, self-care, or any "
        "disposition. Never invent medications or tell the patient to do a self-exam.\n"
        "- If they ask what you mean or 'like what', give 2-4 examples from the packet "
        "that match the current topic, then stop.\n"
        "- Do not treat the question spans as new checklist facts or as an answer to "
        "the asked graph factor.\n"
        f"- Patient question spans: {quoted}\n"
        f"- Knowledge-graph packet:\n{packet}\n\n"
    )


def _build_enrichment_messages(
    *,
    checklist: list[dict[str, Any]],
    latest_user_message: str,
    last_asked_slot: SlotName | None,
    comorbidities_acknowledged: bool,
    last_assistant_message: str = "",
    last_asked_factor: str | None = None,
    factor_states: dict[str, str] | None = None,
    profile: TriageProfile | None = None,
    question_spans: list[str] | None = None,
    graph_packet: str | None = None,
) -> list[dict[str, str]]:
    slot_hint = last_asked_slot or "(none)"
    factor_hint = last_asked_factor or "(none)"
    gap_summary = _coverage_gap_summary(
        checklist=checklist,
        comorbidities_acknowledged=comorbidities_acknowledged,
        last_asked_slot=last_asked_slot,
        latest_user_message=latest_user_message,
        preferred_body_parts=(profile.preferred_body_parts if profile else None),
    )
    exchange = _format_last_exchange_block(
        last_assistant_message=last_assistant_message,
        latest_user_message=latest_user_message,
    )
    instruction = (
        "You are a careful overseer of a structured clinical intake checklist for a "
        "musculoskeletal triage chatbot.\n\n"
        "In ONE response you must (1) maintain the checklist, (2) draft the next "
        "intake question if coverage will still be incomplete after your updates, "
        "and (3) if the patient asked a clarifying question, write patient_answer "
        "from the knowledge-graph packet only. "
        "Do not map findings onto inventory graph Factors — matching is not your job.\n\n"
        "Read the last exchange, existing checklist, coverage gaps, prior factor "
        "states, and the latest patient message. Prior turns are already captured on "
        "the checklist—do not require the full transcript. Maintain the checklist so "
        "it stays accurate and cumulative: add missing facts, correct rows that are "
        "wrong or outdated, and delete rows that the patient clearly retracted or "
        "that were recorded in error.\n\n"
        "Volunteered facts (critical):\n"
        "- Last intake slot asked is a HINT about what the assistant was seeking, NOT a "
        "limit on what you may add or edit.\n"
        "- If a graph factor was asked (Last graph factor asked is not (none)), set "
        "asked_factor_reply to affirmed, denied, unknown, or not_answered. Use "
        "not_answered when the statements do not answer that factor (leave it absent). "
        "Use unknown when they say they do not know. Do not treat a bare "
        "no as filling an HPI slot (palliative, provocative, quality, etc.). Do not "
        "add a checklist row for a denied finding. Denials are not checklist rows.\n"
        "- If the last asked floor slot is palliative, provocative, quality, severity, "
        "duration, age, sex, or comorbidities, and the patient answers nothing / none / "
        "n/a / I don't know / no, add a row for THAT slot with text N/A so coverage "
        "closes (comorbidities: kind=comorbidity, label=comorbidity). "
        "Do not modify or delete an existing N/A row; leave the text as N/A.\n"
        "- Pattern extractors and GliNER often miss or mislabel facts. If the patient "
        "clearly stated something clinically relevant in the last exchange and it is "
        "not already on the checklist with the correct kind/label, you MUST add or "
        "modify a row for it in this turn.\n"
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
        "kind=ner_entity, label=symptom. Do not replace a profile-seeded chief "
        "complaint with a different body area.\n"
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
        "priority still-missing slot and write ONE plain, conversational question for it.\n"
        f"{_next_intake_slot_rules(profile)}"
        "- This order is a hint. The planner may ask a graph-adjacent red-flag "
        "factor instead; still draft the next floor slot so a fallback exists.\n"
        "- Allowed slot values: age | sex | comorbidities | symptom_anchor | "
        "symptom_duration | symptom_severity | symptom_quality | provocative | "
        "palliative.\n"
        "- Output exactly one complete question sentence ending with ?.\n"
        "- Stay on that slot's topic; do not ask about medications unless the slot is "
        "comorbidities.\n"
        "- Do not give triage advice or a diagnosis.\n"
        "- If coverage would be complete after your updates (ready for disposition), "
        "set next_intake to null.\n"
        "- If severity is 7+ or described as severe, do not choose provocative as "
        "next_intake; nothing can make severe pain worse.\n\n"
        f"{_patient_answer_prompt_block(question_spans, graph_packet)}"
        f"Last intake slot asked by assistant: {slot_hint}\n"
        f"Last graph factor asked by assistant: {factor_hint}\n"
        f"Prior factor_states:\n{_format_factor_states_block(factor_states)}\n\n"
        f"Coverage before enrichment:\n{gap_summary}\n\n"
        f"Existing checklist (modify/delete by id in brackets; numbers are display-only):\n"
        f"{_format_checklist_block(checklist)}\n\n"
        f"Last exchange (assistant question + latest patient reply):\n{exchange}\n\n"
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
        '  "next_intake": {"slot": "age", "question": "How old are you?"},\n'
        '  "asked_factor_reply": "not_answered",\n'
        '  "patient_answer": null\n'
        "}\n"
        "Use an empty checklist_operations list when no checklist changes are needed.\n"
        "Set comorbidities_acknowledged to true when the patient denies other health "
        "conditions or says they do not know / none / no / n/a after being asked.\n"
        "Set next_intake to null when no further intake question is needed.\n"
        "Set asked_factor_reply to affirmed | denied | unknown | not_answered | null. "
        "Use not_answered or null when Last graph factor asked is (none) or the "
        "patient did not answer that factor.\n"
        "Set patient_answer to 1-3 graph-packet sentences when the patient asked a "
        "clarifying question; otherwise null."
    )
    return [{"role": "user", "content": instruction}]


def propose_checklist_enrichment(
    *,
    checklist: list[dict[str, Any]],
    conversation_history: list[dict[str, str]] | None = None,
    latest_user_message: str,
    last_asked_slot: SlotName | None = None,
    last_asked_factor: str | None = None,
    comorbidities_acknowledged: bool = False,
    session_id: str = "",
    turn_index: int = 0,
    last_assistant_message: str = "",
    factor_states: dict[str, str] | None = None,
    inventory: tuple[str, ...] | None = None,
    profile: TriageProfile | None = None,
    question_spans: list[str] | None = None,
    graph_packet: str | None = None,
) -> IntakeEnrichmentResult:
    """
    Ask the generator LLM to oversee checklist rows (add / modify / delete)
    and draft the next floor-slot intake question.

    Uses a slim single-message prompt (last exchange + checklist + gaps), not
    full transcript replay. Graph Factor matching is not this model's job.
    """
    checklist = ensure_checklist_ids([dict(r) for r in checklist])
    history = conversation_history or []
    assistant_msg = last_assistant_message.strip() or _last_assistant_from_history(history)

    if not generator_model_configured():
        return IntakeEnrichmentResult(
            status="unavailable",
            summary_reason="Generator LLM not configured; skipped checklist enrichment.",
        )

    try:
        messages = _build_enrichment_messages(
            checklist=checklist,
            latest_user_message=latest_user_message,
            last_asked_slot=last_asked_slot,
            comorbidities_acknowledged=comorbidities_acknowledged,
            last_assistant_message=assistant_msg,
            last_asked_factor=last_asked_factor,
            factor_states=factor_states,
            profile=profile,
            question_spans=question_spans,
            graph_packet=graph_packet,
        )
        raw = generate_from_messages(
            messages,
            max_new_tokens=INTAKE_ENRICH_MAX_NEW_TOKENS,
            temperature=0.15,
            response_mime_type="application/json",
            response_schema=ENRICHMENT_RESPONSE_SCHEMA,
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
    asked_factor_reply = _parse_asked_factor_reply(payload)
    patient_answer = _parse_patient_answer(payload)
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
        preferred_body_parts=(profile.preferred_body_parts if profile else None),
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
        asked_factor_reply=asked_factor_reply,
        patient_answer=patient_answer,
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
