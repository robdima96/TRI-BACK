"""Deterministic credit for direct answers to the asked intake slot."""

from app.orchestrator.coverage import evaluate_checklist_coverage
from app.orchestrator.question_planner import plan_next_question
from app.orchestrator.slot_answers import (
    close_provocative_if_severity_severe,
    credit_asked_slot_answer,
    credit_volunteered_slots,
)
from app.orchestrator.checklist import merge_checklist_items


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


def test_empty_non_answers_fill_asked_slot_as_na():
    items = credit_asked_slot_answer(
        message="I don't know",
        last_asked_slot="palliative",
        checklist=[],
    )
    assert len(items) == 1
    assert items[0].kind == "palliative"
    assert items[0].text == "N/A"


def test_empty_non_answer_with_trailing_punctuation_fills_na():
    items = credit_asked_slot_answer(
        message="I don't know !",
        last_asked_slot="palliative",
        checklist=[],
    )
    assert len(items) == 1
    assert items[0].kind == "palliative"
    assert items[0].text == "N/A"
    dotted = credit_asked_slot_answer(
        message="I don't know.",
        last_asked_slot="palliative",
        checklist=[],
    )
    assert dotted[0].text == "N/A"


def test_bare_no_on_slot_questions_fills_na():
    items = credit_asked_slot_answer(
        message="no",
        last_asked_slot="palliative",
        checklist=[],
    )
    assert len(items) == 1
    assert items[0].text == "N/A"


def test_nothing_fills_provocative_as_na():
    items = credit_asked_slot_answer(
        message="nothing",
        last_asked_slot="provocative",
        checklist=[],
    )
    assert len(items) == 1
    assert items[0].kind == "provocative"
    assert items[0].label == "provocative"
    assert items[0].text == "N/A"
    checklist = [
        {"text": "low back pain", "kind": "ner_entity", "source": "gliner", "label": "symptom"},
        items[0].model_dump(),
    ]
    report, _, _ = evaluate_checklist_coverage(
        checklist=checklist,
        comorbidities_acknowledged=True,
    )
    missing = {m["slot"] for m in report["missing_slots"]}
    assert "provocative" not in missing


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


def test_empty_dont_know_fills_comorbidities_as_na():
    items = credit_asked_slot_answer(
        message="i dont know",
        last_asked_slot="comorbidities",
        checklist=[],
    )
    assert len(items) == 1
    assert items[0].kind == "comorbidity"
    assert items[0].label == "comorbidity"
    assert items[0].text == "N/A"
    checklist = [
        {"text": "30", "kind": "demographic", "source": "pattern", "label": "age"},
        {"text": "male", "kind": "demographic", "source": "pattern", "label": "sex"},
        items[0].model_dump(),
    ]
    report, _, ack = evaluate_checklist_coverage(checklist=checklist)
    assert ack is True
    assert "comorbidities" not in {m["slot"] for m in report["missing_slots"]}
    planned = plan_next_question(
        report, risk_hits=[], questions_asked=1, comorbidities_acknowledged=ack
    )
    assert planned.slot != "comorbidities"


def test_volunteered_60m_fills_age_and_sex_without_copying_into_other_slots():
    items = credit_volunteered_slots(
        message="60M",
        last_asked_slot="age",
        checklist=[],
    )
    labels = {(it.label, it.text.casefold()) for it in items}
    assert ("age", "60") in labels
    assert ("sex", "male") in labels
    assert not any(it.label in {"palliative", "provocative", "symptom_quality"} for it in items)


def test_volunteered_60m_casefolded_and_spaced():
    for msg in ("60m", "60 F", "45f"):
        items = credit_volunteered_slots(
            message=msg,
            last_asked_slot="age",
            checklist=[],
        )
        kinds = {it.label: it.text.casefold() for it in items}
        assert "age" in kinds
        assert kinds["sex"] in {"male", "female"}


def test_volunteered_rejects_60mg():
    items = credit_volunteered_slots(
        message="60mg",
        last_asked_slot="age",
        checklist=[],
    )
    # Free-text may still credit the asked age slot; must not invent sex.
    assert not any(it.label == "sex" for it in items)


def test_volunteered_question_mark_fills_asked_slot_as_na():
    items = credit_volunteered_slots(
        message="?",
        last_asked_slot="age",
        checklist=[],
    )
    assert len(items) == 1
    assert items[0].label == "age"
    assert items[0].text == "N/A"
    assert not any(it.label == "sex" for it in items)


def test_volunteered_mixed_one_liner_fills_several_floor_slots():
    items = credit_volunteered_slots(
        message="I'm 60, male, 6/10, ice helps to ease the pain",
        last_asked_slot="age",
        checklist=[],
    )
    labels = {it.label for it in items}
    assert "age" in labels
    assert "sex" in labels
    assert "symptom_severity" in labels
    assert "palliative" in labels


def test_volunteered_60m_does_not_reask_sex():
    checklist = [
        {"text": "back pain", "kind": "ner_entity", "source": "gliner", "label": "symptom"},
    ]
    credited = credit_volunteered_slots(
        message="60M",
        last_asked_slot="age",
        checklist=checklist,
    )
    merged = merge_checklist_items(checklist, credited)
    report, _, _ = evaluate_checklist_coverage(
        checklist=merged,
        comorbidities_acknowledged=False,
    )
    missing = {m["slot"] for m in report["missing_slots"]}
    assert "age" not in missing
    assert "sex" not in missing
    planned = plan_next_question(
        report, risk_hits=[], questions_asked=1, comorbidities_acknowledged=False
    )
    assert planned.slot != "sex"


def _symptom_with_severity(text: str) -> list[dict[str, str]]:
    return [
        {
            "text": "low back pain",
            "kind": "ner_entity",
            "source": "gliner",
            "label": "symptom",
        },
        {
            "text": text,
            "kind": "severity",
            "source": "pattern",
            "label": "symptom_severity",
        },
    ]


def test_severe_numeric_closes_provocative_as_na():
    for rating in ("7/10", "10/10"):
        closed = close_provocative_if_severity_severe(_symptom_with_severity(rating))
        provoc = [r for r in closed if r.get("label") == "provocative"]
        assert len(provoc) == 1
        assert provoc[0]["text"] == "N/A"
        assert provoc[0]["source"] == "rule"
        report, _, _ = evaluate_checklist_coverage(
            checklist=closed,
            comorbidities_acknowledged=True,
        )
        missing = {m["slot"] for m in report["missing_slots"]}
        assert "provocative" not in missing
        planned = plan_next_question(
            report, risk_hits=[], questions_asked=1, comorbidities_acknowledged=True
        )
        assert planned.slot != "provocative"


def test_severe_word_closes_provocative_as_na():
    closed = close_provocative_if_severity_severe(_symptom_with_severity("severe"))
    provoc = [r for r in closed if r.get("label") == "provocative"]
    assert len(provoc) == 1
    assert provoc[0]["text"] == "N/A"
    report, _, _ = evaluate_checklist_coverage(
        checklist=closed,
        comorbidities_acknowledged=True,
    )
    missing = {m["slot"] for m in report["missing_slots"]}
    assert "provocative" not in missing


def test_mild_or_six_does_not_close_provocative():
    for rating in ("6/10", "mild"):
        closed = close_provocative_if_severity_severe(_symptom_with_severity(rating))
        assert not any(r.get("label") == "provocative" for r in closed)


def test_existing_provocative_kept_when_severity_severe():
    checklist = _symptom_with_severity("8/10") + [
        {
            "text": "worse when sitting",
            "kind": "provocative",
            "source": "pattern",
            "label": "provocative",
        },
    ]
    closed = close_provocative_if_severity_severe(checklist)
    provoc = [r for r in closed if r.get("label") == "provocative"]
    assert len(provoc) == 1
    assert provoc[0]["text"] == "worse when sitting"
