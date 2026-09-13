"""Slot priority and template fallbacks for conversational intake."""

from __future__ import annotations

from app.orchestrator.intake_models import (
    CoverageReport,
    SlotName,
    SymptomInstance,
)

# Floor-only fallback order (matches the ranker when no graph factors compete).
# symptom_anchor is the only real prerequisite; duration ranks last among
# symptom attributes because it opens no graph territory.
_SESSION_ORDER: tuple[SlotName, ...] = ("age", "sex", "comorbidities")
_SYMPTOM_SLOT_ORDER: tuple[SlotName, ...] = (
    "symptom_quality",
    "symptom_severity",
    "provocative",
    "palliative",
    "symptom_duration",
)


def question_template(
    slot: SlotName,
    *,
    display_name: str = "your symptom",
) -> str:
    if slot == "age":
        return "How old are you?"
    if slot == "sex":
        return (
            "What sex were you assigned at birth or how do you identify "
            "(for example male, female, or other)?"
        )
    if slot == "comorbidities":
        return (
            "Do you have any ongoing health conditions "
            "(for example diabetes or arthritis)? If none, say 'none'."
        )
    if slot == "symptom_anchor":
        return "What is your main symptom or body area of concern right now?"
    if slot == "symptom_duration":
        return f"How long has it been since you've had {display_name}?"
    if slot == "symptom_severity":
        return (
            f"On a scale from 0 to 10, how severe is your {display_name} right now?"
        )
    if slot == "symptom_quality":
        return (
            f"How would you describe {display_name} "
            "(for example sharp, dull, aching, burning, or something else)?"
        )
    if slot == "provocative":
        return f"What makes your {display_name} worse?"
    if slot == "palliative":
        return f"What helps your {display_name} feel better?"
    return "Could you tell me a bit more about your symptoms?"


def slot_intake_brief(slot: SlotName, *, display_name: str = "your symptom") -> str:
    """Human-readable description of what the next question must cover."""
    if slot == "age":
        return "the patient's age"
    if slot == "sex":
        return "the patient's sex or gender"
    if slot == "comorbidities":
        return "other ongoing health conditions (not medications unless they mention them)"
    if slot == "symptom_anchor":
        return "their main symptom or body area of concern"
    if slot == "symptom_duration":
        return f"how long they have had {display_name}"
    if slot == "symptom_severity":
        return f"how severe {display_name} is (0–10 scale is fine)"
    if slot == "symptom_quality":
        return f"how {display_name} feels (sharp, dull, aching, burning, etc.)"
    if slot == "provocative":
        return f"what makes {display_name} worse"
    if slot == "palliative":
        return f"what helps {display_name} feel better"
    return "their symptoms"


def _first_missing_for_symptom(
    coverage: CoverageReport, symptom_id: str
) -> SlotName | None:
    for slot in _SYMPTOM_SLOT_ORDER:
        for m in coverage.get("missing_slots") or []:
            if m.get("slot") == slot and m.get("symptom_id") == symptom_id:
                return slot
    return None


def symptom_display_name(
    instances: list[SymptomInstance], symptom_id: str | None
) -> str:
    if not symptom_id:
        return "your symptom"
    for inst in instances:
        if inst["symptom_id"] == symptom_id:
            return inst["display_name"]
    return "your symptom"


def select_next_missing_slot(
    coverage: CoverageReport,
    *,
    comorbidities_acknowledged: bool,
) -> tuple[SlotName | None, str | None]:
    """Pick the highest-priority missing floor slot and optional symptom id.

    Graph factors are ranked separately. This is the floor-only fallback used
    by the enricher consistency guard and by the ranker when budget forces
    floor slots.
    """
    missing_slots = coverage.get("missing_slots") or []
    missing_set = {m["slot"] for m in missing_slots}
    instances = coverage.get("symptom_instances") or []

    if "symptom_anchor" in missing_set or not instances:
        return "symptom_anchor", None

    for slot in _SESSION_ORDER:
        if slot not in missing_set:
            continue
        if slot == "comorbidities" and comorbidities_acknowledged:
            continue
        return slot, coverage.get("active_symptom_id")

    for inst in instances:
        sid = inst["symptom_id"]
        slot = _first_missing_for_symptom(coverage, sid)
        if slot:
            return slot, sid

    return None, coverage.get("active_symptom_id")
