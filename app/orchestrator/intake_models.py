"""Typed structures for conversational intake coverage and question planning."""

from __future__ import annotations

from typing import Literal, NotRequired, TypedDict

# Slots required before triage disposition (RAG + final answer).
SlotName = Literal[
    "age",
    "sex",
    "comorbidities",
    "symptom_anchor",
    "symptom_quality",
    "symptom_severity",
    "symptom_duration",
    "provocative",
    "palliative",
]

# Per-symptom slots required before triage disposition.
REQUIRED_SYMPTOM_SLOTS: tuple[SlotName, ...] = (
    "symptom_quality",
    "symptom_severity",
    "symptom_duration",
    "provocative",
    "palliative",
)

OPTIONAL_SYMPTOM_SLOTS: tuple[SlotName, ...] = ()


class SymptomInstance(TypedDict):
    """One complaint thread derived from a distinct symptom entity in the checklist."""

    symptom_id: str
    display_name: str
    checklist_keys: list[tuple[str, str, str, str]]


class CoverageSlotStatus(TypedDict):
    slot: SlotName
    satisfied: bool
    symptom_id: NotRequired[str]


class CoverageReport(TypedDict):
    session_complete: bool
    symptoms_complete: bool
    ready_for_disposition: bool
    missing_slots: list[CoverageSlotStatus]
    active_symptom_id: str | None
    symptom_instances: list[SymptomInstance]
