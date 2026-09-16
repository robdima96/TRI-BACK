"""Deterministic question planner (one question per turn)."""

from app.config import settings
from app.orchestrator.intake_models import CoverageReport
from app.orchestrator.intake_slots import question_template
from app.orchestrator.question_planner import (
    INSUFFICIENT_INFO_REASON,
    plan_next_question,
)


def _coverage(**kwargs) -> CoverageReport:
    base: CoverageReport = {
        "session_complete": False,
        "symptoms_complete": False,
        "ready_for_disposition": False,
        "missing_slots": [],
        "active_symptom_id": None,
        "symptom_instances": [],
    }
    base.update(kwargs)  # type: ignore[typeddict-item]
    return base


def test_planner_asks_symptom_anchor_before_age():
    """Unassumed coverage (no profile seed) still elicits a chief complaint first."""
    cov = _coverage(
        missing_slots=[
            {"slot": "age", "satisfied": False},
            {"slot": "symptom_anchor", "satisfied": False},
        ]
    )
    planned = plan_next_question(
        cov, risk_hits=[], questions_asked=0, comorbidities_acknowledged=False
    )
    assert planned.question_mode is True
    assert planned.slot == "symptom_anchor"
    assert planned.next_question == question_template("symptom_anchor")
    assert planned.question_reason and "rank:t0:symptom_anchor" in planned.question_reason


def test_planner_asks_age_when_anchor_is_filled():
    cov = _coverage(missing_slots=[{"slot": "age", "satisfied": False}])
    planned = plan_next_question(
        cov, risk_hits=[], questions_asked=0, comorbidities_acknowledged=False
    )
    assert planned.question_mode is True
    assert planned.slot == "age"
    assert planned.next_question == question_template("age")
    assert planned.question_reason and planned.question_reason.startswith("template_fallback:")


def test_planner_uses_combined_intake_draft_when_slot_matches():
    cov = _coverage(missing_slots=[{"slot": "age", "satisfied": False}])
    planned = plan_next_question(
        cov,
        risk_hits=[],
        questions_asked=0,
        comorbidities_acknowledged=False,
        pending_question="How old are you today?",
        pending_slot="age",
    )
    assert planned.question_mode is True
    assert planned.slot == "age"
    assert planned.next_question == "How old are you today?"
    assert planned.question_reason and planned.question_reason.startswith("combined_intake:")


def test_planner_ignores_mismatched_pending_slot():
    cov = _coverage(missing_slots=[{"slot": "age", "satisfied": False}])
    planned = plan_next_question(
        cov,
        risk_hits=[],
        questions_asked=0,
        comorbidities_acknowledged=False,
        pending_question="What sex were you assigned at birth?",
        pending_slot="sex",
    )
    assert planned.question_mode is True
    assert planned.slot == "age"
    assert planned.next_question == question_template("age")
    assert planned.question_reason and planned.question_reason.startswith("template_fallback:")


def test_planner_risk_skips_questions():
    cov = _coverage(missing_slots=[{"slot": "age", "satisfied": False}])
    planned = plan_next_question(
        cov, risk_hits=["chest_pain"], questions_asked=0, comorbidities_acknowledged=False
    )
    assert planned.question_mode is False
    assert planned.next_question is None
    assert planned.question_reason == "risk_escalation"


def test_planner_max_questions_forces_disposition_path():
    cov = _coverage(missing_slots=[{"slot": "age", "satisfied": False}])
    planned = plan_next_question(
        cov,
        risk_hits=[],
        questions_asked=settings.max_questions,
        comorbidities_acknowledged=False,
    )
    assert planned.question_mode is False
    assert planned.question_reason == "max_questions_reached"


def test_planner_max_questions_with_unknown_ces_is_insufficient_info():
    cov = _coverage(
        ready_for_disposition=True,
        missing_slots=[],
        symptom_instances=[
            {"symptom_id": "s1", "display_name": "low back pain", "checklist_keys": []}
        ],
        active_symptom_id="s1",
    )
    planned = plan_next_question(
        cov,
        risk_hits=[],
        questions_asked=settings.max_questions,
        comorbidities_acknowledged=True,
        factor_states={"Neuro sensory deficit": "affirmed"},
    )
    assert planned.question_mode is False
    assert planned.question_reason == INSUFFICIENT_INFO_REASON


def test_planner_asks_graph_factor_after_floor_is_complete():
    cov = _coverage(
        session_complete=True,
        symptoms_complete=True,
        ready_for_disposition=True,
        missing_slots=[],
        symptom_instances=[
            {"symptom_id": "s1", "display_name": "low back pain", "checklist_keys": []}
        ],
        active_symptom_id="s1",
    )
    planned = plan_next_question(
        cov,
        risk_hits=[],
        questions_asked=9,
        comorbidities_acknowledged=True,
        factor_states={"Neuro sensory deficit": "affirmed"},
    )
    assert planned.question_mode is True
    assert planned.slot is None
    assert planned.asked_factor
    assert planned.question_reason and planned.question_reason.startswith("rank:t1:CES:")


def test_planner_coverage_complete_when_floor_met_and_no_factors():
    cov = _coverage(
        session_complete=True,
        symptoms_complete=True,
        ready_for_disposition=True,
        missing_slots=[],
        symptom_instances=[
            {"symptom_id": "s1", "display_name": "low back pain", "checklist_keys": []}
        ],
        active_symptom_id="s1",
    )
    planned = plan_next_question(
        cov,
        risk_hits=[],
        questions_asked=9,
        comorbidities_acknowledged=True,
        factor_states={},
    )
    assert planned.question_mode is False
    assert planned.question_reason == "coverage_complete"


def test_force_hook_is_separate_from_slot_planner():
    from app.orchestrator.question_planner import plan_forced_factor_question

    cov = _coverage(missing_slots=[{"slot": "age", "satisfied": False}])
    planned = plan_next_question(
        cov, risk_hits=[], questions_asked=0, comorbidities_acknowledged=False
    )
    assert planned.slot == "age"
    forced = plan_forced_factor_question("Saddle anaesthesia")
    assert forced is not None
    assert forced[2] == "Saddle anaesthesia"
    assert planned.question_mode is True
    assert planned.next_question != forced[0]
