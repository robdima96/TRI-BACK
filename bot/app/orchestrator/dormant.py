"""Post-disposition dormant phase: canned replies until symptoms change."""

from __future__ import annotations

import re
from typing import Any

from app.orchestrator.slot_answers import _EMPTY_ANSWER

INTAKE_PHASE = "intake"
DORMANT_PHASE = "dormant"

DORMANT_REPLY = (
    "I was built to help you navigate the healthcare system. "
    "Have your symptoms changed?"
)

_SYMPTOM_KINDS = frozenset(
    {
        "symptom",
        "symptom_quality",
        "severity",
        "duration",
        "provocative",
        "palliative",
    }
)
_SYMPTOM_LABELS = frozenset(
    {
        "symptom",
        "body part",
        "symptom quality",
        "symptom severity",
        "symptom duration",
        "symptom provocative factor",
        "symptom palliative factor",
        "sign",
    }
)

# Affirmative / worsening language after the canned "have your symptoms changed?"
_CHANGE_AFFIRM = re.compile(
    r"(?:"
    r"^\s*(?:yes|yeah|yep|yup)\s*[.!]?\s*$"
    r"|it'?s\s+worse|they(?:'ve|\s+have)\s+changed|the\s+pain\s+is\s+worse"
    r"|now\s+my\s+|going\s+down\s+my\s+"
    r")",
    re.I,
)


def _row_key(row: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(row.get("text") or ""),
        str(row.get("kind") or ""),
        str(row.get("source") or ""),
        str(row.get("label") or ""),
    )


def _is_symptom_row(row: dict[str, Any]) -> bool:
    if str(row.get("kind") or "").casefold() in _SYMPTOM_KINDS:
        return True
    return str(row.get("label") or "").casefold() in _SYMPTOM_LABELS


def detect_symptom_change(
    *,
    message: str,
    prior_checklist: list[dict[str, Any]],
    merged_checklist: list[dict[str, Any]],
) -> bool:
    """True when this turn adds/modifies symptom rows or the user affirms change."""
    text = (message or "").strip()
    if _CHANGE_AFFIRM.search(text):
        return True
    if _EMPTY_ANSWER.match(text or ""):
        return False
    prior_keys = {_row_key(r) for r in prior_checklist if _is_symptom_row(r)}
    for row in merged_checklist:
        if not _is_symptom_row(row):
            continue
        if _row_key(row) not in prior_keys:
            return True
    return False


def is_dormant_phase(state: dict[str, Any]) -> bool:
    return (state.get("session_phase") or INTAKE_PHASE) == DORMANT_PHASE
