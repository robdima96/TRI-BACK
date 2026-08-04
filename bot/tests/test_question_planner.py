"""Deterministic question planner (one question per turn)."""

from app.config import settings
from app.orchestrator.intake_models import CoverageReport
from app.orchestrator.intake_slots import question_template
from app.orchestrator.question_planner import plan_next_question


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


def test_planner_asks_age_first():
    cov = _coverage(missing_slots=[{"slot": "age", "satisfied": False}])
    mode, q, reason, slot, _ = plan_next_question(
        cov, risk_hits=[], questions_asked=0, comorbidities_acknowledged=False
    )
    assert mode is True
    assert slot == "age"
    assert q == question_template("age")
    assert reason and reason.startswith("template_fallback:")


def test_planner_uses_combined_intake_draft_when_slot_matches():
    cov = _coverage(missing_slots=[{"slot": "age", "satisfied": False}])
    mode, q, reason, slot, _ = plan_next_question(
        cov,
        risk_hits=[],
        questions_asked=0,
        comorbidities_acknowledged=False,
        pending_question="How old are you today?",
        pending_slot="age",
    )
    assert mode is True
    assert slot == "age"
    assert q == "How old are you today?"
    assert reason and reason.startswith("combined_intake:")


def test_planner_ignores_mismatched_pending_slot():
    cov = _coverage(missing_slots=[{"slot": "age", "satisfied": False}])
    mode, q, reason, slot, _ = plan_next_question(
        cov,
        risk_hits=[],
        questions_asked=0,
        comorbidities_acknowledged=False,
        pending_question="What sex were you assigned at birth?",
        pending_slot="sex",
    )
    assert mode is True
    assert slot == "age"
    assert q == question_template("age")
    assert reason and reason.startswith("template_fallback:")


def test_planner_risk_skips_questions():
    cov = _coverage(missing_slots=[{"slot": "age", "satisfied": False}])
    mode, q, reason, _, _ = plan_next_question(
        cov, risk_hits=["chest_pain"], questions_asked=0, comorbidities_acknowledged=False
    )
    assert mode is False
    assert q is None
    assert reason == "risk_escalation"


def test_planner_max_questions_forces_disposition_path():
    cov = _coverage(missing_slots=[{"slot": "age", "satisfied": False}])
    mode, _, reason, _, _ = plan_next_question(
        cov,
        risk_hits=[],
        questions_asked=settings.max_questions,
        comorbidities_acknowledged=False,
    )
    assert mode is False
    assert reason == "max_questions_reached"
