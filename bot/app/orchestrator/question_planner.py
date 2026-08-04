"""LLM-backed next-question selection from coverage gaps (one question per turn).

The intake LLM call is folded into checklist enrichment
(``propose_checklist_enrichment``), which drafts ``pending_question`` for a
candidate slot. This planner remains authoritative for *which* slot to ask;
it only uses the pending draft when it matches that slot, otherwise it falls
back to the deterministic template — never a second generator round-trip.
"""

from __future__ import annotations

from app.config import settings
from app.orchestrator.intake_models import CoverageReport, SlotName
from app.orchestrator.intake_slots import (
    question_template,
    select_next_missing_slot,
    symptom_display_name,
)
from app.services.intake_llm import _question_matches_slot, _sanitize_question


def plan_next_question(
    coverage: CoverageReport,
    *,
    risk_hits: list[str],
    questions_asked: int,
    comorbidities_acknowledged: bool,
    checklist: list[dict[str, str]] | None = None,
    conversation_history: list[dict[str, str]] | None = None,
    latest_user_message: str = "",
    pending_question: str | None = None,
    pending_slot: SlotName | None = None,
) -> tuple[bool, str | None, str | None, SlotName | None, str | None]:
    """
    Decide whether to ask one intake question or proceed to disposition.

    Returns:
        ``(question_mode, next_question, question_reason, slot, active_symptom_id)``
    """
    # Unused by the combined-call path; kept for call-site compatibility.
    _ = (checklist, conversation_history, latest_user_message)

    if risk_hits:
        return False, None, "risk_escalation", None, coverage.get("active_symptom_id")

    if questions_asked >= settings.max_questions:
        return False, None, "max_questions_reached", None, coverage.get(
            "active_symptom_id"
        )

    if coverage.get("ready_for_disposition"):
        return False, None, "coverage_complete", None, coverage.get("active_symptom_id")

    slot, active_id = select_next_missing_slot(
        coverage, comorbidities_acknowledged=comorbidities_acknowledged
    )
    if slot is None:
        return False, None, "no_plannable_gap", None, coverage.get("active_symptom_id")

    instances = coverage.get("symptom_instances") or []
    display = symptom_display_name(instances, active_id)
    fallback = question_template(slot, display_name=display)
    reason_base = f"missing:{slot}"
    if active_id:
        reason_base = f"{reason_base}:symptom={active_id}"

    if pending_slot == slot and pending_question:
        question = _sanitize_question(pending_question)
        if question and _question_matches_slot(question, slot):
            return True, question, f"combined_intake:{reason_base}", slot, active_id

    return True, fallback, f"template_fallback:{reason_base}", slot, active_id
