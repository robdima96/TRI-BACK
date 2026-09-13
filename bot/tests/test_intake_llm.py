"""LLM intake question generation."""

from unittest.mock import patch

from app.orchestrator.intake_models import CoverageReport
from app.orchestrator.intake_slots import question_template, select_next_missing_slot
from app.services.intake_llm import (
    _sanitize_question,
    generate_intake_question,
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


def test_select_promotes_comorbidities_over_symptom_slots():
    cov = _coverage(
        symptom_instances=[
            {"symptom_id": "s1", "display_name": "low back pain", "checklist_keys": []}
        ],
        missing_slots=[
            {"slot": "comorbidities", "satisfied": False},
            {"slot": "symptom_duration", "satisfied": False, "symptom_id": "s1"},
        ],
    )
    slot, sid = select_next_missing_slot(cov, comorbidities_acknowledged=False)
    assert slot == "comorbidities"


@patch("app.services.intake_llm.generate_from_messages")
def test_intake_llm_rejects_off_topic_medication_question(mock_gen):
    mock_gen.return_value = "What other medical conditions or medications do you have?"
    cov = _coverage(
        symptom_instances=[
            {"symptom_id": "s1", "display_name": "low back pain", "checklist_keys": []}
        ],
        active_symptom_id="s1",
    )
    question, reason = generate_intake_question(
        checklist=[],
        conversation_history=[],
        coverage=cov,
        latest_user_message="I fell yesterday",
        slot="symptom_duration",
        active_symptom_id="s1",
    )
    assert question == question_template("symptom_duration", display_name="low back pain")
    assert reason.startswith("template_fallback:")


def test_sanitize_question_prefers_longest_complete_line():
    raw = "How would you?\nHow would you describe your lower back pain?"
    assert _sanitize_question(raw) == "How would you describe your lower back pain?"


def test_sanitize_question_rejects_truncated_fragment():
    assert _sanitize_question("How would") == ""
    assert _sanitize_question("How would?") == ""
    assert _sanitize_question("Could you describe how?") == ""


def test_sanitize_question_strips_cot_tags():
    raw = (
        "<thinking>pick wording</thinking>\n"
        "<answer>How long have you had your back pain?</answer>"
    )
    assert _sanitize_question(raw) == "How long have you had your back pain?"


@patch("app.services.intake_llm.generate_from_messages")
def test_intake_llm_falls_back_on_truncated_model_output(mock_gen):
    mock_gen.return_value = "How would"
    cov = _coverage(
        symptom_instances=[
            {"symptom_id": "s1", "display_name": "pain", "checklist_keys": []}
        ],
        active_symptom_id="s1",
    )
    question, reason = generate_intake_question(
        checklist=[],
        conversation_history=[],
        coverage=cov,
        latest_user_message="I fell yesterday",
        slot="symptom_quality",
        active_symptom_id="s1",
    )
    assert question == question_template("symptom_quality", display_name="pain")
    assert reason.startswith("template_fallback:")
