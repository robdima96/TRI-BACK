"""Checklist coverage evaluator: session + per-symptom completeness for triage disposition."""

from __future__ import annotations

import re

from app.orchestrator.intake_models import (
    OPTIONAL_SYMPTOM_SLOTS,
    REQUIRED_SYMPTOM_SLOTS,
    CoverageReport,
    CoverageSlotStatus,
    SlotName,
    SymptomInstance,
)

# checklist row identity (matches merge_checklist_items dedupe key)
ChecklistKey = tuple[str, str, str, str]

_NONE_COMORBIDITY = re.compile(
    r"\b(?:no|none|nothing|n/?a|don't have any|do not have any)\b",
    re.I,
)


def _row_key(row: dict[str, str]) -> ChecklistKey:
    return (
        row.get("text", ""),
        row.get("kind", ""),
        row.get("source", ""),
        row.get("label", ""),
    )


def _normalize_key(key: ChecklistKey | list[str]) -> ChecklistKey:
    """LangGraph JSON checkpoints deserialize tuple keys as lists."""
    if isinstance(key, list):
        parts = [str(x) for x in key]
        while len(parts) < 4:
            parts.append("")
        return (parts[0], parts[1], parts[2], parts[3])
    return key


def _is_symptom_entity_row(row: dict[str, str]) -> bool:
    """Each GliNER symptom span becomes its own symptom instance (not body-part only)."""
    return row.get("kind") == "ner_entity" and row.get("label", "").casefold() == "symptom"


def _rows_for_kind_label(
    checklist: list[dict[str, str]],
    *,
    kind: str,
    label: str | None = None,
) -> list[ChecklistKey]:
    out: list[ChecklistKey] = []
    for row in checklist:
        if row.get("kind") != kind:
            continue
        if label is not None and row.get("label", "") != label:
            continue
        out.append(_row_key(row))
    return out


# rebuild symptom instances from merged checklist (one row per distinct symptom entity text)
def build_symptom_instances(
    checklist: list[dict[str, str]],
    *,
    prior_instances: list[SymptomInstance] | None = None,
) -> list[SymptomInstance]:
    """
    Derive symptom instances from checklist rows.

    Every ``ner_entity`` with label ``symptom`` is its own instance; stable ids are
    preserved across turns when display text matches a prior instance.
    """
    prior_by_name: dict[str, SymptomInstance] = {}
    if prior_instances:
        for inst in prior_instances:
            prior_by_name[inst["display_name"].casefold()] = inst

    seen_text: set[str] = set()
    instances: list[SymptomInstance] = []
    next_idx = 1
    for row in checklist:
        if not _is_symptom_entity_row(row):
            continue
        text = (row.get("text") or "").strip()
        if not text:
            continue
        key = text.casefold()
        if key in seen_text:
            continue
        seen_text.add(key)
        ck = _row_key(row)
        if key in prior_by_name:
            inst = dict(prior_by_name[key])
            keys = [_normalize_key(k) for k in (inst.get("checklist_keys") or [])]
            if ck not in keys:
                keys.append(ck)
            inst["checklist_keys"] = keys
            instances.append(inst)
            continue
        sid = f"s{next_idx}"
        next_idx += 1
        instances.append(
            SymptomInstance(
                symptom_id=sid,
                display_name=text,
                checklist_keys=[ck],
            )
        )
    return instances


def consolidate_symptom_instances(
    instances: list[SymptomInstance],
) -> list[SymptomInstance]:
    """
    Intake focuses on one chief complaint.

    GliNER may emit several ``symptom`` spans (pain, bruising, tenderness, …).
    For questioning we keep a single primary instance (prefer pain/ache wording).
    """
    if len(instances) <= 1:
        return instances

    pain_related = [
        inst
        for inst in instances
        if any(token in inst["display_name"].casefold() for token in ("pain", "ache"))
    ]
    pool = pain_related if pain_related else instances
    primary = max(pool, key=lambda inst: len(inst["display_name"]))
    primary_id = pool[0]["symptom_id"]

    merged_keys: list[ChecklistKey] = []
    seen: set[ChecklistKey] = set()
    for inst in instances:
        for key in inst.get("checklist_keys") or []:
            normalized = _normalize_key(key)
            if normalized in seen:
                continue
            seen.add(normalized)
            merged_keys.append(normalized)

    return [
        SymptomInstance(
            symptom_id=primary_id,
            display_name=primary["display_name"],
            checklist_keys=merged_keys,
        )
    ]


def _merge_assignments_after_consolidation(
    prior_assignments: dict[str, dict[str, list[ChecklistKey]]] | None,
    raw_instances: list[SymptomInstance],
    consolidated: list[SymptomInstance],
) -> dict[str, dict[str, list[ChecklistKey]]] | None:
    """Fold per-symptom slot keys into the single instance after consolidation."""
    if not prior_assignments or len(raw_instances) <= 1 or len(consolidated) != 1:
        return prior_assignments
    target_id = consolidated[0]["symptom_id"]
    merged: dict[str, list[ChecklistKey]] = {
        slot: [] for slot in (*REQUIRED_SYMPTOM_SLOTS, *OPTIONAL_SYMPTOM_SLOTS)
    }
    seen_by_slot: dict[str, set[ChecklistKey]] = {slot: set() for slot in merged}
    for inst in raw_instances:
        slot_map = prior_assignments.get(inst["symptom_id"]) or {}
        for slot, keys in slot_map.items():
            if slot not in merged:
                continue
            for key in keys:
                normalized = _normalize_key(key)
                if normalized in seen_by_slot[slot]:
                    continue
                seen_by_slot[slot].add(normalized)
                merged[slot].append(normalized)
    return {target_id: merged}


_GLINER_LABELS_FOR_SLOT: dict[SlotName, frozenset[str]] = {
    "symptom_duration": frozenset({"symptom duration"}),
    "symptom_severity": frozenset({"symptom severity"}),
    "symptom_quality": frozenset({"symptom quality"}),
    "provocative": frozenset({"symptom provocative factor"}),
    "palliative": frozenset({"symptom palliative factor"}),
}


def _rows_for_attribute_slot(
    checklist: list[dict[str, str]],
    slot: SlotName,
) -> list[ChecklistKey]:
    """Pattern rows plus matching GliNER attribute labels for a symptom slot."""
    kind_label = _ATTR_KINDS.get(slot)
    keys: list[ChecklistKey] = []
    seen: set[ChecklistKey] = set()
    if kind_label:
        kind, label = kind_label
        for key in _rows_for_kind_label(checklist, kind=kind, label=label):
            if key not in seen:
                seen.add(key)
                keys.append(key)
    for gliner_label in _GLINER_LABELS_FOR_SLOT.get(slot, frozenset()):
        for row in checklist:
            if row.get("kind") != "ner_entity":
                continue
            if row.get("label", "").casefold() != gliner_label:
                continue
            key = _row_key(row)
            if key not in seen:
                seen.add(key)
                keys.append(key)
    return keys


_ATTR_KINDS: dict[SlotName, tuple[str, str | None]] = {
    "symptom_quality": ("symptom_quality", "symptom_quality"),
    "symptom_severity": ("severity", "symptom_severity"),
    "symptom_duration": ("duration", "duration"),
    "provocative": ("provocative", "provocative"),
    "palliative": ("palliative", "palliative"),
}


def _keys_in_checklist(checklist: list[dict[str, str]], key: ChecklistKey | list[str]) -> bool:
    normalized = _normalize_key(key)
    return normalized in {_row_key(r) for r in checklist}


# attach attribute rows per symptom (strict multi-symptom via persisted assignments)
def _link_attribute_keys(
    checklist: list[dict[str, str]],
    instances: list[SymptomInstance],
    *,
    active_symptom_id: str | None,
    prior_assignments: dict[str, dict[str, list[ChecklistKey]]] | None = None,
) -> dict[str, dict[SlotName, list[ChecklistKey]]]:
    """
    Map per-symptom slot -> checklist keys.

    Single symptom: all checklist attributes belong to that instance. Multiple
    symptoms: keep prior assignments, then assign newly seen keys to
    ``active_symptom_id`` (or the instance missing the most required slots).
    """
    by_symptom: dict[str, dict[SlotName, list[ChecklistKey]]] = {
        inst["symptom_id"]: {slot: [] for slot in (*REQUIRED_SYMPTOM_SLOTS, *OPTIONAL_SYMPTOM_SLOTS)}
        for inst in instances
    }
    if not instances:
        return by_symptom

    assigned_globally: set[ChecklistKey] = set()
    if prior_assignments:
        for sid, slot_map in prior_assignments.items():
            if sid not in by_symptom:
                continue
            for slot, keys in slot_map.items():
                if slot not in by_symptom[sid]:
                    continue
                kept = [_normalize_key(k) for k in keys if _keys_in_checklist(checklist, k)]
                by_symptom[sid][slot] = kept  # type: ignore[literal-required]
                assigned_globally.update(kept)

    if len(instances) == 1:
        sid = instances[0]["symptom_id"]
        for slot in _ATTR_KINDS:
            by_symptom[sid][slot] = _rows_for_attribute_slot(checklist, slot)  # type: ignore[literal-required]
        return by_symptom

    for slot in _ATTR_KINDS:
        available = [
            k
            for k in _rows_for_attribute_slot(checklist, slot)
            if k not in assigned_globally
        ]
        for key in available:
            target = active_symptom_id if active_symptom_id in by_symptom else None
            if not target:
                target = _pick_instance_for_slot(by_symptom, instances, slot)
            by_symptom[target][slot].append(key)
            assigned_globally.add(key)

    return by_symptom


def _pick_instance_for_slot(
    by_symptom: dict[str, dict[SlotName, list[ChecklistKey]]],
    instances: list[SymptomInstance],
    slot: SlotName,
) -> str:
    """Assign an attribute row to the instance missing this slot (required first)."""
    for inst in instances:
        sid = inst["symptom_id"]
        if not by_symptom[sid].get(slot):
            return sid
    return instances[0]["symptom_id"]


def _session_slots_status(
    checklist: list[dict[str, str]],
    *,
    comorbidities_acknowledged: bool,
) -> tuple[list[CoverageSlotStatus], bool]:
    missing: list[CoverageSlotStatus] = []
    age_ok = bool(_rows_for_kind_label(checklist, kind="demographic", label="age"))
    sex_ok = bool(_rows_for_kind_label(checklist, kind="demographic", label="sex"))
    comorb_ok = comorbidities_acknowledged or bool(
        _rows_for_kind_label(checklist, kind="comorbidity")
    )
    if not age_ok:
        missing.append(CoverageSlotStatus(slot="age", satisfied=False))
    if not sex_ok:
        missing.append(CoverageSlotStatus(slot="sex", satisfied=False))
    if not comorb_ok:
        missing.append(CoverageSlotStatus(slot="comorbidities", satisfied=False))
    session_complete = age_ok and sex_ok and comorb_ok
    return missing, session_complete


def _symptom_slots_status(
    instances: list[SymptomInstance],
    linked: dict[str, dict[SlotName, list[ChecklistKey]]],
) -> tuple[list[CoverageSlotStatus], bool]:
    """Strict disposition: every symptom instance must satisfy all required slots."""
    missing: list[CoverageSlotStatus] = []
    if not instances:
        missing.append(CoverageSlotStatus(slot="symptom_anchor", satisfied=False))
        return missing, False

    all_complete = True
    for inst in instances:
        sid = inst["symptom_id"]
        slots = linked.get(sid, {})
        for slot in REQUIRED_SYMPTOM_SLOTS:
            if slots.get(slot):
                continue
            all_complete = False
            missing.append(
                CoverageSlotStatus(slot=slot, satisfied=False, symptom_id=sid)
            )
    return missing, all_complete


# public evaluator used by evaluate_coverage_node
def assignments_from_linked(
    linked: dict[str, dict[SlotName, list[ChecklistKey]]],
) -> dict[str, dict[str, list[ChecklistKey]]]:
    """Serialize slot assignments for checkpoint persistence."""
    return {
        sid: {slot: list(keys) for slot, keys in slot_map.items()}
        for sid, slot_map in linked.items()
    }


def evaluate_checklist_coverage(
    *,
    checklist: list[dict[str, str]],
    comorbidities_acknowledged: bool = False,
    symptom_instances: list[SymptomInstance] | None = None,
    active_symptom_id: str | None = None,
    last_asked_slot: SlotName | None = None,
    latest_user_message: str = "",
    symptom_slot_assignments: dict[str, dict[str, list[ChecklistKey]]] | None = None,
) -> tuple[
    CoverageReport,
    dict[str, dict[str, list[ChecklistKey]]],
    bool,
]:
    """
    Rebuild symptom instances, link attribute rows, and compute disposition readiness.

    Updates ``comorbidities_acknowledged`` when the user clearly denies comorbidities
    after a comorbidity intake question.
    """
    ack = comorbidities_acknowledged or bool(
        _rows_for_kind_label(checklist, kind="comorbidity")
    )
    if (
        not ack
        and last_asked_slot == "comorbidities"
        and latest_user_message.strip()
        and _NONE_COMORBIDITY.search(latest_user_message)
    ):
        ack = True

    raw_instances = build_symptom_instances(
        checklist, prior_instances=symptom_instances
    )
    instances = consolidate_symptom_instances(raw_instances)
    merged_prior = _merge_assignments_after_consolidation(
        symptom_slot_assignments, raw_instances, instances
    )
    linked = _link_attribute_keys(
        checklist,
        instances,
        active_symptom_id=active_symptom_id,
        prior_assignments=merged_prior,
    )
    new_assignments = assignments_from_linked(linked)
    session_missing, session_complete = _session_slots_status(
        checklist, comorbidities_acknowledged=ack
    )
    symptom_missing, symptoms_complete = _symptom_slots_status(instances, linked)

    missing = session_missing + symptom_missing
    ready = session_complete and symptoms_complete and bool(instances)

    active = active_symptom_id
    if instances and active not in {i["symptom_id"] for i in instances}:
        active = instances[-1]["symptom_id"]

    report = CoverageReport(
        session_complete=session_complete,
        symptoms_complete=symptoms_complete,
        ready_for_disposition=ready,
        missing_slots=missing,
        active_symptom_id=active,
        symptom_instances=instances,
    )
    return report, new_assignments, ack


def coverage_intake_summary(coverage: CoverageReport) -> str:
    """Short text summary of known intake for the disposition generator prompt."""
    lines: list[str] = []
    if coverage.get("ready_for_disposition"):
        lines.append("Intake coverage: complete (ready for disposition).")
    else:
        lines.append("Intake coverage: incomplete.")
    for inst in coverage.get("symptom_instances") or []:
        lines.append(f"- Symptom: {inst['display_name']} ({inst['symptom_id']})")
    missing = coverage.get("missing_slots") or []
    if missing:
        parts = [
            m["slot"] if "symptom_id" not in m else f"{m['slot']}@{m['symptom_id']}"
            for m in missing[:12]
        ]
        lines.append(f"Still missing: {', '.join(parts)}")
    return "\n".join(lines)
