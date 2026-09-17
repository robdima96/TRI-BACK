"""Phase 3 relevance ranker: neighbourhood, tiers, floor guard, coherence."""

from __future__ import annotations

from app.config import settings
from app.orchestrator.intake_models import CoverageReport
from app.orchestrator.question_planner import plan_next_question
from app.orchestrator.relevance_ranker import (
    NON_SEED_FACTORS,
    TIER_SYMPTOM_SLOTS,
    TIER_TIME_CRITICAL,
    apply_coherence_guard,
    clinical_finding_seeds,
    eligible_neighbour_factors,
    floor_budget_exhausted,
    rank_question_candidates,
)
from app.services.agentic_graph_rag.ontology import load_ontology


def _coverage(**kwargs) -> CoverageReport:
    base: CoverageReport = {
        "session_complete": False,
        "symptoms_complete": False,
        "ready_for_disposition": False,
        "missing_slots": [],
        "active_symptom_id": "s1",
        "symptom_instances": [
            {"symptom_id": "s1", "display_name": "low back pain", "checklist_keys": []}
        ],
    }
    base.update(kwargs)  # type: ignore[typeddict-item]
    return base


def _symptom_gaps() -> list[dict]:
    return [
        {"slot": "symptom_quality", "satisfied": False, "symptom_id": "s1"},
        {"slot": "symptom_severity", "satisfied": False, "symptom_id": "s1"},
        {"slot": "symptom_duration", "satisfied": False, "symptom_id": "s1"},
        {"slot": "provocative", "satisfied": False, "symptom_id": "s1"},
        {"slot": "palliative", "satisfied": False, "symptom_id": "s1"},
    ]


def test_tingling_opens_ces_neighbourhood():
    ont = load_ontology()
    neighbours = eligible_neighbour_factors(
        {"Neuro sensory deficit": "affirmed"},
        ontology=ont,
    )
    assert "Saddle anaesthesia" in neighbours
    assert "Bladder dysfunction" in neighbours
    assert "Bowel dysfunction" in neighbours
    assert "Endothelial injury" not in neighbours
    assert "Hypercoagulability" not in neighbours
    assert "Age over 50" not in neighbours


def test_non_seed_factors_do_not_open_neighbourhood():
    ont = load_ontology()
    assert "Hypertension" in NON_SEED_FACTORS
    assert "Severe pain" in NON_SEED_FACTORS
    for name in NON_SEED_FACTORS:
        seeds = clinical_finding_seeds({name: "affirmed"}, ontology=ont)
        assert seeds == ()
        neighbours = eligible_neighbour_factors({name: "affirmed"}, ontology=ont)
        assert neighbours == ()


def test_denied_factor_is_not_a_candidate():
    ont = load_ontology()
    neighbours = eligible_neighbour_factors(
        {
            "Neuro sensory deficit": "affirmed",
            "Saddle anaesthesia": "denied",
        },
        ontology=ont,
    )
    assert "Saddle anaesthesia" not in neighbours
    assert "Bladder dysfunction" in neighbours


def test_explicit_unknown_factor_is_not_a_candidate():
    ont = load_ontology()
    neighbours = eligible_neighbour_factors(
        {
            "Neuro sensory deficit": "affirmed",
            "Saddle anaesthesia": "unknown",
        },
        ontology=ont,
    )
    assert "Saddle anaesthesia" not in neighbours
    assert "Bladder dysfunction" in neighbours


def test_ces_after_tingling_outranks_symptom_slots():
    cov = _coverage(missing_slots=_symptom_gaps())
    planned = plan_next_question(
        cov,
        risk_hits=[],
        questions_asked=3,
        comorbidities_acknowledged=True,
        factor_states={"Neuro sensory deficit": "affirmed"},
    )
    assert planned.question_mode is True
    assert planned.slot is None
    assert planned.asked_factor
    assert planned.question_reason and planned.question_reason.startswith("rank:t1:CES:")
    ont = load_ontology()
    assert planned.asked_factor in ont.factors_by_condition["CES"]
    spec = ont.get_factor_question_spec(planned.asked_factor)
    assert spec is not None and spec.askable


def test_no_neuro_means_no_ces_question():
    cov = _coverage(missing_slots=_symptom_gaps())
    planned = plan_next_question(
        cov,
        risk_hits=[],
        questions_asked=3,
        comorbidities_acknowledged=True,
        factor_states={},
    )
    assert planned.question_mode is True
    assert planned.asked_factor is None
    assert planned.slot == "symptom_quality"
    assert planned.question_reason and "rank:t4:symptom_quality" in planned.question_reason


def test_duration_ranks_last_among_symptom_slots():
    cov = _coverage(
        missing_slots=[
            {"slot": "symptom_duration", "satisfied": False, "symptom_id": "s1"},
            {"slot": "palliative", "satisfied": False, "symptom_id": "s1"},
            {"slot": "provocative", "satisfied": False, "symptom_id": "s1"},
        ]
    )
    ranked = rank_question_candidates(cov, {}, floor_only=True)
    names = [c.name for c in ranked if c.kind == "slot"]
    assert names == ["provocative", "palliative", "symptom_duration"]


def test_floor_guard_blocks_factor_when_budget_equals_remaining_floor():
    gaps = _symptom_gaps()
    assert floor_budget_exhausted(
        questions_asked=settings.max_questions - len(gaps),
        max_questions=settings.max_questions,
        remaining_floor=len(gaps),
    )
    cov = _coverage(missing_slots=gaps)
    planned = plan_next_question(
        cov,
        risk_hits=[],
        questions_asked=settings.max_questions - len(gaps),
        comorbidities_acknowledged=True,
        factor_states={"Neuro sensory deficit": "affirmed"},
    )
    assert planned.question_mode is True
    assert planned.asked_factor is None
    assert planned.slot in {
        "symptom_quality",
        "symptom_severity",
        "provocative",
        "palliative",
        "symptom_duration",
    }


def test_tier1_preempts_hysteresis():
    cov = _coverage(missing_slots=_symptom_gaps())
    ranked = rank_question_candidates(
        cov,
        {"Neuro sensory deficit": "affirmed"},
        last_topic="symptom:s1",
        last_tier=TIER_SYMPTOM_SLOTS,
    )
    assert ranked
    assert ranked[0].kind == "factor"
    assert ranked[0].tier == TIER_TIME_CRITICAL
    assert ranked[0].condition == "CES"


def test_hysteresis_keeps_symptom_topic_over_mechanical_factors():
    # Incumbent is a T4 symptom line. A T5 candidate must not yank the topic.
    from app.orchestrator.relevance_ranker import RankedCandidate

    quality = RankedCandidate(
        kind="slot",
        name="symptom_quality",
        tier=TIER_SYMPTOM_SLOTS,
        topic="symptom:s1",
        reason="rank:t4:symptom_quality",
        symptom_id="s1",
    )
    mechanical = RankedCandidate(
        kind="factor",
        name="Movement-related pain",
        tier=5,
        topic="condition:Non-specific Mechanical Cause",
        reason="rank:t5:Non-specific Mechanical Cause:Movement-related pain",
        condition="Non-specific Mechanical Cause",
    )
    chosen = apply_coherence_guard(
        [mechanical, quality],
        last_topic="symptom:s1",
        last_tier=TIER_SYMPTOM_SLOTS,
    )
    assert chosen is quality


def test_hypertension_does_not_open_dvt_or_aaa_questions():
    ont = load_ontology()
    neighbours = eligible_neighbour_factors(
        {
            "Age over 50": "affirmed",
            "Male sex": "affirmed",
            "Hypertension": "affirmed",
            "Severe pain": "affirmed",
        },
        ontology=ont,
    )
    assert neighbours == ()
    assert "Previous DVT" not in neighbours
    assert "Family history of AAA" not in neighbours


def test_abdominal_pain_still_seeds_aaa_when_hypertension_is_also_affirmed():
    ont = load_ontology()
    neighbours = eligible_neighbour_factors(
        {
            "Hypertension": "affirmed",
            "Abdominal pain": "affirmed",
        },
        ontology=ont,
    )
    assert "Family history of AAA" in neighbours
    assert "Cardiovascular disease" in neighbours


def test_six_of_ten_and_denied_abdominal_pain_do_not_open_aaa():
    ont = load_ontology()
    neighbours = eligible_neighbour_factors(
        {
            "Age over 50": "affirmed",
            "Male sex": "affirmed",
            "Severe pain": "denied",
            "Abdominal pain": "denied",
            "Prolonged sitting aggravates": "affirmed",
        },
        ontology=ont,
    )
    assert "Family history of AAA" not in neighbours
    assert "Cardiovascular disease" not in neighbours
    assert "Previous DVT" not in neighbours


def test_non_askable_never_emitted():
    ont = load_ontology()
    neighbours = eligible_neighbour_factors(
        {"Diabetes": "affirmed"},
        ontology=ont,
    )
    for name in neighbours:
        spec = ont.get_factor_question_spec(name)
        assert spec is not None
        assert spec.askable
    assert "Hypercoagulability" not in neighbours
    assert "Venous stasis" not in neighbours
    assert "Endothelial injury" not in neighbours
