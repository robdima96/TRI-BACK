"""Factor-question plumbing (Phase 2): asked_factor credit via the test hook."""

from __future__ import annotations

from unittest.mock import patch

from app.orchestrator.factor_answers import credit_asked_factor_answer
from app.orchestrator.nodes import (
    enrich_checklist_node,
    generate_question_node,
    plan_question_node,
)
from app.orchestrator.question_planner import plan_forced_factor_question
from app.orchestrator.slot_answers import credit_asked_slot_answer
from app.services.intake_enricher import IntakeEnrichmentResult


def test_force_hook_rejects_non_askable():
    assert plan_forced_factor_question("Endothelial injury") is None
    assert plan_forced_factor_question("Hypercoagulability") is None
    assert plan_forced_factor_question("not a factor") is None


def test_force_hook_returns_saddle_fallback():
    planned = plan_forced_factor_question("Saddle anaesthesia")
    assert planned is not None
    question, reason, factor = planned
    assert factor == "Saddle anaesthesia"
    assert reason == "force_factor_ask:Saddle anaesthesia"
    assert "saddle" in question.casefold() or "groin" in question.casefold()
    assert question.endswith("?")


def test_credit_factor_yes_no_unknown():
    yes = credit_asked_factor_answer(
        message="yes",
        asked_factor="Saddle anaesthesia",
        factor_states={},
    )
    assert yes["Saddle anaesthesia"] == "affirmed"

    no = credit_asked_factor_answer(
        message="no",
        asked_factor="Saddle anaesthesia",
        factor_states={},
    )
    assert no["Saddle anaesthesia"] == "denied"

    unsure = credit_asked_factor_answer(
        message="not sure",
        asked_factor="Saddle anaesthesia",
        factor_states={},
    )
    assert unsure["Saddle anaesthesia"] == "unknown"


def test_bare_no_to_factor_is_not_credited_to_slot():
    states = credit_asked_factor_answer(
        message="no",
        asked_factor="Saddle anaesthesia",
        factor_states={},
    )
    assert states["Saddle anaesthesia"] == "denied"
    assert (
        credit_asked_slot_answer(
            message="no",
            last_asked_slot="palliative",
            checklist=[],
        )
        == []
    )


def _plan_state(**overrides):
    state = {
        "session_id": "sess-factor-ask",
        "coverage": {
            "session_complete": False,
            "symptoms_complete": False,
            "ready_for_disposition": False,
            "missing_slots": [{"slot": "age", "satisfied": False}],
            "active_symptom_id": None,
            "symptom_instances": [],
        },
        "risk_hits": [],
        "questions_asked": 0,
        "comorbidities_acknowledged": False,
        "clinical_checklist": [],
        "messages": [],
        "message_normalized": "",
        "pending_intake_question": None,
        "pending_intake_slot": None,
        "last_asked_slot": "palliative",
        "force_factor_ask": "Saddle anaesthesia",
    }
    state.update(overrides)
    return state


def test_forced_factor_ask_parks_last_asked_slot():
    state = plan_question_node(_plan_state())
    assert state["question_mode"] is True
    assert state["slot_being_asked"] is None
    assert state["asked_factor"] == "Saddle anaesthesia"
    assert state["force_factor_ask"] is None
    assert "saddle" in (state["next_question"] or "").casefold() or "groin" in (
        (state["next_question"] or "").casefold()
    )

    out = generate_question_node(state)
    assert out["last_asked_slot"] is None
    assert out["asked_factor"] == "Saddle anaesthesia"
    assert out["questions_asked"] == 1


def test_forced_factor_ask_round_trip_no_does_not_fill_slot():
    asked = generate_question_node(plan_question_node(_plan_state()))
    asked["message"] = "no"
    asked["message_normalized"] = "no"
    asked["turn_start_checklist"] = []
    asked["clinical_checklist"] = []
    asked["encoder_turn_items"] = []
    asked["extraction_history"] = []
    asked["messages"] = []

    enrichment = IntakeEnrichmentResult(
        status="unavailable",
        summary_reason="skipped",
    )
    with patch(
        "app.orchestrator.nodes.propose_checklist_enrichment",
        return_value=enrichment,
    ) as mocked:
        out = enrich_checklist_node(asked)
        kwargs = mocked.call_args.kwargs
        assert kwargs["last_asked_slot"] is None
        assert kwargs["last_asked_factor"] == "Saddle anaesthesia"

    assert (out.get("factor_states") or {}).get("Saddle anaesthesia") == "denied"
    assert not any(row.get("kind") == "palliative" for row in out["clinical_checklist"])
    assert out["last_asked_slot"] is None


def test_forced_factor_ask_round_trip_yes_and_not_sure():
    enrichment = IntakeEnrichmentResult(status="unavailable", summary_reason="skipped")

    yes_state = generate_question_node(plan_question_node(_plan_state()))
    yes_state.update(
        {
            "message": "yes",
            "message_normalized": "yes",
            "turn_start_checklist": [],
            "clinical_checklist": [],
            "encoder_turn_items": [],
            "extraction_history": [],
            "messages": [],
        }
    )
    with patch(
        "app.orchestrator.nodes.propose_checklist_enrichment",
        return_value=enrichment,
    ):
        yes_out = enrich_checklist_node(yes_state)
    assert yes_out["factor_states"]["Saddle anaesthesia"] == "affirmed"

    unsure_state = generate_question_node(plan_question_node(_plan_state()))
    unsure_state.update(
        {
            "message": "not sure",
            "message_normalized": "not sure",
            "turn_start_checklist": [],
            "clinical_checklist": [],
            "encoder_turn_items": [],
            "extraction_history": [],
            "messages": [],
        }
    )
    with patch(
        "app.orchestrator.nodes.propose_checklist_enrichment",
        return_value=enrichment,
    ):
        unsure_out = enrich_checklist_node(unsure_state)
    assert unsure_out["factor_states"]["Saddle anaesthesia"] == "unknown"
