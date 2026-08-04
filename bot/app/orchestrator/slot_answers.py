"""Credit free-text answers to the intake slot the assistant just asked.

When the patient answers a palliative/provocative (etc.) question with a short
phrase like "Exercise", pattern cues such as "better with" are often absent.
Without this fallback, coverage keeps the slot missing and the planner re-asks
— even when the patient already answered clearly.
"""

from __future__ import annotations

import re

from app.orchestrator.intake_models import SlotName
from app.schemas import ChecklistItem

# Slots where a direct free-text reply to the prior question should fill coverage
# even without encoder cue phrases.
_CREDITABLE_SLOTS: frozenset[SlotName] = frozenset(
    {
        "palliative",
        "provocative",
        "symptom_quality",
        "symptom_severity",
        "symptom_duration",
        "symptom_anchor",
        "age",
        "sex",
    }
)

_SLOT_KIND_LABEL: dict[SlotName, tuple[str, str]] = {
    "palliative": ("palliative", "palliative"),
    "provocative": ("provocative", "provocative"),
    "symptom_quality": ("symptom_quality", "symptom_quality"),
    "symptom_severity": ("severity", "symptom_severity"),
    "symptom_duration": ("duration", "duration"),
    "symptom_anchor": ("ner_entity", "symptom"),
    "age": ("demographic", "age"),
    "sex": ("demographic", "sex"),
}

# GliNER labels that also satisfy attribute slots (mirrors coverage.py).
_GLINER_LABELS: dict[SlotName, frozenset[str]] = {
    "symptom_duration": frozenset({"symptom duration"}),
    "symptom_severity": frozenset({"symptom severity"}),
    "symptom_quality": frozenset({"symptom quality"}),
    "provocative": frozenset({"symptom provocative factor"}),
    "palliative": frozenset({"symptom palliative factor"}),
}

# Non-answers that should not close a clinical slot.
_EMPTY_ANSWER = re.compile(
    r"^\s*(?:i\s+don'?t\s+know|idk|unsure|not\s+sure|n/?a|nothing|none|"
    r"no\s+idea|\?+)\s*$",
    re.I,
)


def _has_kind_label(
    checklist: list[dict[str, str]], *, kind: str, label: str
) -> bool:
    want = label.casefold()
    for row in checklist:
        if row.get("kind") != kind:
            continue
        if (row.get("label") or "").casefold() == want:
            return True
    return False


def _slot_already_filled(checklist: list[dict[str, str]], slot: SlotName) -> bool:
    kind_label = _SLOT_KIND_LABEL.get(slot)
    if not kind_label:
        return False
    kind, label = kind_label
    if _has_kind_label(checklist, kind=kind, label=label):
        return True
    for gliner_label in _GLINER_LABELS.get(slot, frozenset()):
        if _has_kind_label(checklist, kind="ner_entity", label=gliner_label):
            return True
    if slot == "symptom_anchor":
        return any(r.get("kind") == "symptom" for r in checklist)
    return False


def credit_asked_slot_answer(
    *,
    message: str,
    last_asked_slot: SlotName | None,
    checklist: list[dict[str, str]],
) -> list[ChecklistItem]:
    """Return checklist rows that credit ``message`` to ``last_asked_slot`` if needed."""
    if not last_asked_slot or last_asked_slot not in _CREDITABLE_SLOTS:
        return []
    text = (message or "").strip()
    if not text or _EMPTY_ANSWER.match(text):
        return []
    if _slot_already_filled(checklist, last_asked_slot):
        return []

    kind_label = _SLOT_KIND_LABEL.get(last_asked_slot)
    if not kind_label:
        return []
    kind, label = kind_label
    # Keep short, readable answers; truncate runaway paste.
    snippet = text if len(text) <= 120 else text[:117].rstrip() + "..."
    return [
        ChecklistItem(
            text=snippet,
            kind=kind,
            source="slot_answer",
            label=label,
        )
    ]
