"""Deterministic credit for direct answers to the asked intake slot."""

from app.orchestrator.coverage import evaluate_checklist_coverage
from app.orchestrator.slot_answers import credit_asked_slot_answer


def test_credits_bare_exercise_after_palliative_ask():
    checklist = [
        {"text": "low back pain", "kind": "ner_entity", "source": "gliner", "label": "symptom"},
    ]
    items = credit_asked_slot_answer(
        message="Exercise",
        last_asked_slot="palliative",
        checklist=checklist,
    )
    assert len(items) == 1
    assert items[0].kind == "palliative"
    assert items[0].text == "Exercise"
    assert items[0].source == "slot_answer"


def test_skips_when_palliative_already_present():
    checklist = [
        {"text": "improved by", "kind": "palliative", "source": "pattern", "label": "palliative"},
    ]
    items = credit_asked_slot_answer(
        message="Exercise",
        last_asked_slot="palliative",
        checklist=checklist,
    )
    assert items == []


def test_skips_empty_non_answers():
    assert (
        credit_asked_slot_answer(
            message="I don't know",
            last_asked_slot="palliative",
            checklist=[],
        )
        == []
    )


def test_credited_row_satisfies_coverage():
    base = [
        {"text": "40", "kind": "demographic", "source": "pattern", "label": "age"},
        {"text": "male", "kind": "demographic", "source": "pattern", "label": "sex"},
        {"text": "low back pain", "kind": "ner_entity", "source": "gliner", "label": "symptom"},
        {"text": "2 weeks", "kind": "duration", "source": "pattern", "label": "duration"},
        {"text": "7/10", "kind": "severity", "source": "pattern", "label": "symptom_severity"},
        {
            "text": "aching",
            "kind": "symptom_quality",
            "source": "pattern",
            "label": "symptom_quality",
        },
        {
            "text": "worse when sitting",
            "kind": "provocative",
            "source": "pattern",
            "label": "provocative",
        },
    ]
    credited = credit_asked_slot_answer(
        message="Exercise",
        last_asked_slot="palliative",
        checklist=base,
    )
    checklist = base + [it.model_dump() for it in credited]
    report, _, _ = evaluate_checklist_coverage(
        checklist=checklist,
        comorbidities_acknowledged=True,
    )
    missing = {m["slot"] for m in report["missing_slots"]}
    assert "palliative" not in missing
    assert report["symptoms_complete"] is True
