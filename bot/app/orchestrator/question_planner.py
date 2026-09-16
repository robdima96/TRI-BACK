"""LLM-backed next-question selection from coverage gaps (one question per turn).

The intake LLM call is folded into checklist enrichment
(``propose_checklist_enrichment``), which drafts ``pending_question`` for a
candidate slot. This planner remains authoritative for *which* slot or factor
to ask; it only uses the pending draft when it matches that target, otherwise
it falls back to the deterministic template — never a second generator round-trip.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.config import settings
from app.orchestrator.intake_models import CoverageReport, SlotName
from app.orchestrator.intake_slots import (
    question_template,
    symptom_display_name,
)
from app.orchestrator.relevance_ranker import (
    RankedCandidate,
    floor_budget_exhausted,
    has_unknown_time_critical,
    rank_question_candidates,
    remaining_floor_count,
)
from app.services.agentic_graph_rag.ontology import (
    FactorQuestionSpec,
    RedFlagOntology,
    get_factor_question_spec,
)
from app.triage_profiles import TriageProfile, load_ontology_for_profile
from app.services.intake_llm import _question_matches_slot, _sanitize_question

INSUFFICIENT_INFO_REASON = "insufficient_info_time_critical"


@dataclass(frozen=True)
class PlannedQuestion:
    question_mode: bool
    next_question: str | None
    question_reason: str | None
    slot: SlotName | None
    active_symptom_id: str | None
    asked_factor: str | None = None
    rank_topic: str | None = None
    rank_tier: int | None = None


def _disposition(
    reason: str,
    coverage: CoverageReport,
    *,
    active_id: str | None = None,
) -> PlannedQuestion:
    return PlannedQuestion(
        question_mode=False,
        next_question=None,
        question_reason=reason,
        slot=None,
        active_symptom_id=active_id if active_id is not None else coverage.get("active_symptom_id"),
    )


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
    factor_states: dict[str, str] | None = None,
    matched_factors: list[str] | None = None,
    last_rank_topic: str | None = None,
    last_rank_tier: int | None = None,
    profile: TriageProfile | None = None,
) -> PlannedQuestion:
    """
    Decide whether to ask one intake question or proceed to disposition.

    Ranker runs before the coverage-complete return so a finished floor can
    still receive an eligible graph question. ``max_questions`` consults
    remaining time-critical neighbourhood before emitting a clinical dump.
    """
    _ = (checklist, conversation_history, latest_user_message, comorbidities_acknowledged)

    if risk_hits:
        return _disposition("risk_escalation", coverage)

    ontology = load_ontology_for_profile(profile)
    remaining_floor = remaining_floor_count(coverage)
    floor_only = floor_budget_exhausted(
        questions_asked=questions_asked,
        max_questions=settings.max_questions,
        remaining_floor=remaining_floor,
    )
    ranked = rank_question_candidates(
        coverage,
        factor_states,
        matched_factors=matched_factors,
        ontology=ontology,
        last_topic=last_rank_topic,
        last_tier=last_rank_tier,
        floor_only=floor_only,
        profile=profile,
    )

    if questions_asked >= settings.max_questions:
        if has_unknown_time_critical(
            factor_states,
            matched_factors=matched_factors,
            ontology=ontology,
            profile=profile,
        ):
            return _disposition(INSUFFICIENT_INFO_REASON, coverage)
        return _disposition("max_questions_reached", coverage)

    if not ranked:
        if remaining_floor == 0:
            return _disposition("coverage_complete", coverage)
        return _disposition("no_plannable_gap", coverage)

    winner = ranked[0]
    if winner.kind == "factor":
        return _plan_factor_question(
            winner,
            coverage,
            pending_question=pending_question,
            ontology=ontology,
        )
    return _plan_slot_question(
        winner,
        coverage,
        pending_question=pending_question,
        pending_slot=pending_slot,
    )


def _plan_slot_question(
    winner: RankedCandidate,
    coverage: CoverageReport,
    *,
    pending_question: str | None,
    pending_slot: SlotName | None,
) -> PlannedQuestion:
    slot: SlotName = winner.name  # type: ignore[assignment]
    active_id = winner.symptom_id or coverage.get("active_symptom_id")
    instances = coverage.get("symptom_instances") or []
    display = symptom_display_name(instances, active_id)
    fallback = question_template(slot, display_name=display)
    reason = winner.reason

    if pending_slot == slot and pending_question:
        question = _sanitize_question(pending_question)
        if question and _question_matches_slot(question, slot):
            return PlannedQuestion(
                question_mode=True,
                next_question=question,
                question_reason=f"combined_intake:{reason}",
                slot=slot,
                active_symptom_id=active_id,
                asked_factor=None,
                rank_topic=winner.topic,
                rank_tier=winner.tier,
            )

    return PlannedQuestion(
        question_mode=True,
        next_question=fallback,
        question_reason=f"template_fallback:{reason}",
        slot=slot,
        active_symptom_id=active_id,
        asked_factor=None,
        rank_topic=winner.topic,
        rank_tier=winner.tier,
    )


def _plan_factor_question(
    winner: RankedCandidate,
    coverage: CoverageReport,
    *,
    pending_question: str | None,
    ontology: RedFlagOntology,
) -> PlannedQuestion:
    spec = get_factor_question_spec(winner.name, ontology=ontology)
    if spec is None or not spec.askable or not spec.fallback:
        return _disposition("no_plannable_gap", coverage)
    question, phrasing = _factor_question_text(
        spec,
        pending_question=pending_question,
        reason=winner.reason,
    )
    return PlannedQuestion(
        question_mode=True,
        next_question=question,
        question_reason=phrasing,
        slot=None,
        active_symptom_id=coverage.get("active_symptom_id"),
        asked_factor=spec.factor,
        rank_topic=winner.topic,
        rank_tier=winner.tier,
    )


def _content_tokens(*blobs: str) -> set[str]:
    tokens: set[str] = set()
    for blob in blobs:
        tokens.update(
            t for t in re.findall(r"[a-z0-9]+", (blob or "").casefold()) if len(t) > 3
        )
    return tokens


def _question_matches_factor(question: str, spec: FactorQuestionSpec) -> bool:
    if not (question or "").strip().endswith("?"):
        return False
    hay = question.casefold()
    needles = _content_tokens(spec.intent, spec.fallback, *spec.synonyms)
    return bool(needles) and any(n in hay for n in needles)


def _factor_question_text(
    spec: FactorQuestionSpec,
    *,
    pending_question: str | None,
    reason: str,
) -> tuple[str, str]:
    if pending_question:
        drafted = _sanitize_question(pending_question)
        if drafted and _question_matches_factor(drafted, spec):
            return drafted, f"combined_intake:{reason}"
    return spec.fallback, reason


def plan_forced_factor_question(
    factor: str,
    *,
    pending_question: str | None = None,
) -> tuple[str, str, str] | None:
    """Test/debug hook: return ``(question, reason, canonical_factor)``.

    Live intake does not call this. A missing spec or ``askable=no`` is not a
    legal ask target and returns None so the caller can fall through to slots.
    """
    name = (factor or "").strip()
    if not name:
        return None
    spec = get_factor_question_spec(name)
    if spec is None or not spec.askable or not spec.fallback:
        return None
    if pending_question:
        drafted = _sanitize_question(pending_question)
        if drafted and _question_matches_factor(drafted, spec):
            return drafted, f"force_factor_ask:{spec.factor}", spec.factor
    return spec.fallback, f"force_factor_ask:{spec.factor}", spec.factor
