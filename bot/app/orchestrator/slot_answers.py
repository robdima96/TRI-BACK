"""Credit free-text answers to intake slots the patient already answered.

When the patient answers a palliative/provocative (etc.) question with a short
phrase like "Exercise", pattern cues such as "better with" are often absent.
Without this fallback, coverage keeps the slot missing and the planner re-asks
— even when the patient already answered clearly.

The asked slot still gets that free-text credit. Other still-missing creditable
slots are filled only when the same message independently answers them (so a
compact reply like ``60M`` can close age *and* sex without dumping the whole
utterance into quality/palliative).
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
        "comorbidities",
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
    "comorbidities": ("comorbidity", "comorbidity"),
}

# GliNER labels that also satisfy attribute slots (mirrors coverage.py).
_GLINER_LABELS: dict[SlotName, frozenset[str]] = {
    "symptom_duration": frozenset({"symptom duration"}),
    "symptom_severity": frozenset({"symptom severity"}),
    "symptom_quality": frozenset({"symptom quality"}),
    "provocative": frozenset({"symptom provocative factor"}),
    "palliative": frozenset({"symptom palliative factor"}),
}

# Empty / none-style replies. On an asked floor slot these close coverage as N/A.
# A bare "no" is a real answer to a factor question (see factor_answers) and must
# not reach this helper while a graph factor is being asked.
# Trailing . / ! is allowed so "I don't know !" still counts as empty.
_EMPTY_ANSWER = re.compile(
    r"^\s*(?:i\s+don'?t\s+know|idk|unsure|not\s+sure|n/?a|nothing|none|"
    r"no\s+idea|\?+|no|nope|nah)\s*[.!]*\s*$",
    re.I,
)

NA_SLOT_TEXT = "N/A"

# Kinds whose empty-answer text should stay canonical N/A (floor HPI slots).
_FLOOR_SLOT_KINDS: frozenset[str] = frozenset(
    {
        "palliative",
        "provocative",
        "symptom_quality",
        "severity",
        "duration",
        "demographic",
        "comorbidity",
    }
)


def is_empty_slot_answer(text: str) -> bool:
    """True when ``text`` is a whole-message empty / unsure slot reply."""
    return bool(_EMPTY_ANSWER.match(text or ""))


def is_na_slot_text(text: str) -> bool:
    return str(text or "").strip() == NA_SLOT_TEXT


def canonicalize_floor_slot_text(kind: str, text: str) -> str:
    """Map empty-answer utterances on floor-slot kinds to ``N/A``."""
    if kind in _FLOOR_SLOT_KINDS and is_empty_slot_answer(text):
        return NA_SLOT_TEXT
    return text

# Compact clinical token: digits plus an optional leftover used with _SEX_CANONICAL.
_COMPACT_AGE = re.compile(r"^(\d{1,3})(.*)$", re.I)
_LEADING_AGE = re.compile(r"^\s*(\d{1,3})\b")


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


def _severity_row_texts(checklist: list[dict[str, str]]) -> list[str]:
    texts: list[str] = []
    for row in checklist:
        kind = str(row.get("kind") or "")
        label = str(row.get("label") or "").casefold()
        if kind == "severity" and label == "symptom_severity":
            texts.append(str(row.get("text") or ""))
        elif kind == "ner_entity" and label == "symptom severity":
            texts.append(str(row.get("text") or ""))
    return texts


def _row_fills_slot(row: dict[str, str], slot: SlotName) -> bool:
    kind_label = _SLOT_KIND_LABEL.get(slot)
    if not kind_label:
        return False
    kind, label = kind_label
    row_kind = str(row.get("kind") or "")
    row_label = str(row.get("label") or "").casefold()
    if row_kind == kind and row_label == label.casefold():
        return True
    for gliner_label in _GLINER_LABELS.get(slot, frozenset()):
        if row_kind == "ner_entity" and row_label == gliner_label.casefold():
            return True
    if slot == "symptom_anchor" and row_kind == "symptom":
        return True
    return False


def drop_this_turn_rows_for_slot(
    checklist: list[dict[str, str]],
    *,
    prior_checklist: list[dict[str, str]],
    slot: SlotName | None,
) -> list[dict[str, str]]:
    """Remove this-turn candidate rows that fill ``slot`` (unusable answers)."""
    if not slot or slot not in _SLOT_KIND_LABEL:
        return [dict(row) for row in checklist]
    prior_ids = {str(row.get("id")) for row in prior_checklist if row.get("id")}
    prior_keys = {
        (
            str(row.get("text") or ""),
            str(row.get("kind") or ""),
            str(row.get("source") or ""),
            str(row.get("label") or ""),
        )
        for row in prior_checklist
    }
    kept: list[dict[str, str]] = []
    for row in checklist:
        item = dict(row)
        if not _row_fills_slot(item, slot):
            kept.append(item)
            continue
        row_id = str(item.get("id") or "")
        key = (
            str(item.get("text") or ""),
            str(item.get("kind") or ""),
            str(item.get("source") or ""),
            str(item.get("label") or ""),
        )
        if row_id and row_id in prior_ids:
            kept.append(item)
        elif not row_id and key in prior_keys:
            kept.append(item)
    return kept


def close_provocative_if_severity_severe(
    checklist: list[dict[str, str]],
) -> list[dict[str, str]]:
    """If pain is already severe (7+ or severe wording), close provocative as N/A."""
    from app.orchestrator.checklist import merge_checklist_items
    from app.services.rag.factor_patterns import _severity_implies_severe

    working = [dict(row) for row in checklist]
    if _slot_already_filled(working, "provocative"):
        return working
    if not any(_severity_implies_severe(text) for text in _severity_row_texts(working)):
        return working
    row = _row_for_slot("provocative", NA_SLOT_TEXT, source="rule")
    if row is None:
        return working
    return merge_checklist_items(working, [row])


def _snippet(text: str) -> str:
    return text if len(text) <= 120 else text[:117].rstrip() + "..."


def _row_for_slot(slot: SlotName, text: str, *, source: str = "slot_answer") -> ChecklistItem | None:
    kind_label = _SLOT_KIND_LABEL.get(slot)
    if not kind_label or not text.strip():
        return None
    kind, label = kind_label
    return ChecklistItem(
        text=_snippet(text.strip()),
        kind=kind,
        source=source,
        label=label,
    )


def _age_years(raw: str) -> str | None:
    try:
        years = int(raw)
    except ValueError:
        return None
    if 1 <= years <= 120:
        return str(years)
    return None


def _sex_from_canonical_leftover(leftover: str) -> str | None:
    from app.services.encoder import _SEX_CANONICAL, _canonical_sex_text

    token = leftover.strip(" .,-/")
    if not token:
        return None
    low = token.casefold()
    if low in _SEX_CANONICAL:
        return _SEX_CANONICAL[low]
    mapped = _canonical_sex_text(token)
    if mapped and mapped.casefold() in _SEX_CANONICAL.values():
        return mapped
    return None


def _independent_items(slot: SlotName, message: str) -> list[ChecklistItem]:
    """Fill ``slot`` only when the message independently answers it."""
    from app.services.encoder import (
        _SEX_VALUE_WORDS,
        _canonical_sex_text,
        _pattern_demographics_age,
        _pattern_demographics_sex,
        _pattern_durations,
        _pattern_pall,
        _pattern_provoc,
        _pattern_quality,
        _pattern_severity,
    )

    text = (message or "").strip()
    if not text:
        return []

    if slot == "age":
        items = list(_pattern_demographics_age(text))
        if items:
            return items
        compact = _COMPACT_AGE.match(text.replace(" ", ""))
        if compact:
            years = _age_years(compact.group(1))
            leftover = compact.group(2) or ""
            # Only treat as age when leftover is empty or a sex letter (60 / 60M),
            # not units like mg/ml.
            if years and (not leftover or _sex_from_canonical_leftover(leftover)):
                row = _row_for_slot("age", years)
                return [row] if row else []
        leading = _LEADING_AGE.match(text)
        if leading and _pattern_demographics_age(text):
            return _pattern_demographics_age(text)
        return []

    if slot == "sex":
        items = list(_pattern_demographics_sex(text))
        if items:
            return items
        word = re.search(rf"\b({_SEX_VALUE_WORDS})\b", text, re.I)
        if word:
            mapped = _canonical_sex_text(word.group(1))
            row = _row_for_slot("sex", mapped)
            return [row] if row else []
        compact = _COMPACT_AGE.match(text.replace(" ", ""))
        if compact:
            leftover = compact.group(2) or ""
            mapped = _sex_from_canonical_leftover(leftover)
            if mapped and _age_years(compact.group(1)):
                row = _row_for_slot("sex", mapped)
                return [row] if row else []
        return []

    if slot == "symptom_quality":
        return list(_pattern_quality(text))
    if slot == "symptom_severity":
        return list(_pattern_severity(text))
    if slot == "symptom_duration":
        return list(_pattern_durations(text))
    if slot == "provocative":
        return list(_pattern_provoc(text))
    if slot == "palliative":
        return list(_pattern_pall(text))
    return []


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
    if not text:
        return []
    if is_empty_slot_answer(text):
        if _slot_already_filled(checklist, last_asked_slot):
            return []
        row = _row_for_slot(last_asked_slot, NA_SLOT_TEXT)
        return [row] if row else []
    if _slot_already_filled(checklist, last_asked_slot):
        return []

    independent = _independent_items(last_asked_slot, text)
    if independent:
        return independent

    row = _row_for_slot(last_asked_slot, text)
    return [row] if row else []


def credit_volunteered_slots(
    *,
    message: str,
    last_asked_slot: SlotName | None,
    checklist: list[dict[str, str]],
) -> list[ChecklistItem]:
    """Credit the asked slot plus any other missing slots the message answers."""
    text = (message or "").strip()
    if not text:
        return []

    out: list[ChecklistItem] = []
    working = list(checklist)

    asked = credit_asked_slot_answer(
        message=text,
        last_asked_slot=last_asked_slot,
        checklist=working,
    )
    for item in asked:
        out.append(item)
        working.append(item.model_dump())

    if is_empty_slot_answer(text):
        return out

    for slot in (
        "age",
        "sex",
        "symptom_anchor",
        "symptom_quality",
        "symptom_severity",
        "symptom_duration",
        "provocative",
        "palliative",
    ):
        if slot == last_asked_slot:
            continue
        if slot not in _CREDITABLE_SLOTS:
            continue
        if _slot_already_filled(working, slot):
            continue
        extra = _independent_items(slot, text)
        for item in extra:
            if _slot_already_filled(working, slot):
                break
            out.append(item)
            working.append(item.model_dump())
    return out
