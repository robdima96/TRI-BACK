"""Checklist coverage evaluator for conversational intake."""

from app.orchestrator.coverage import evaluate_checklist_coverage


def _row(text: str, kind: str, label: str, source: str = "pattern") -> dict[str, str]:
    return {"text": text, "kind": kind, "source": source, "label": label}


def test_session_slots_age_sex_comorbidity():
    checklist = [
        _row("40", "demographic", "age"),
        _row("male", "demographic", "sex"),
        _row("diabetes", "comorbidity", "comorbidity"),
    ]
    report, _, ack = evaluate_checklist_coverage(checklist=checklist)
    assert report["session_complete"] is True
    assert ack is True  # comorbidity row sets acknowledged


def test_symptom_entity_creates_instance():
    checklist = [
        _row("low back pain", "ner_entity", "symptom", "gliner"),
    ]
    report, _, _ = evaluate_checklist_coverage(checklist=checklist)
    assert len(report["symptom_instances"]) == 1
    assert report["symptom_instances"][0]["display_name"] == "low back pain"
    assert report["ready_for_disposition"] is False


def test_strict_requires_all_symptoms_complete():
    checklist = [
        _row("40", "demographic", "age"),
        _row("male", "demographic", "sex"),
        _row("low back pain", "ner_entity", "symptom", "gliner"),
        _row("3 months", "duration", "duration"),
        _row("7/10", "severity", "symptom_severity"),
        _row("aching", "symptom_quality", "symptom_quality"),
        _row("worse when bending", "provocative", "provocative"),
        _row("rest helps", "palliative", "palliative"),
    ]
    report, _, _ = evaluate_checklist_coverage(
        checklist=checklist,
        comorbidities_acknowledged=True,
    )
    assert report["session_complete"] is True
    assert report["symptoms_complete"] is True
    assert report["ready_for_disposition"] is True


def test_provocative_palliative_required():
    base = [
        _row("40", "demographic", "age"),
        _row("male", "demographic", "sex"),
        _row("knee pain", "ner_entity", "symptom", "gliner"),
        _row("2 weeks", "duration", "duration"),
        _row("5/10", "severity", "symptom_severity"),
        _row("sharp", "symptom_quality", "symptom_quality"),
    ]
    report, _, _ = evaluate_checklist_coverage(
        checklist=base,
        comorbidities_acknowledged=True,
    )
    assert report["symptoms_complete"] is False
    missing = {m["slot"] for m in report["missing_slots"]}
    assert "provocative" in missing
    assert "palliative" in missing

    complete = base + [
        _row("worse when walking", "provocative", "provocative"),
        _row("ice helps", "palliative", "palliative"),
    ]
    report, _, _ = evaluate_checklist_coverage(
        checklist=complete,
        comorbidities_acknowledged=True,
    )
    assert report["symptoms_complete"] is True


def test_prior_assignments_with_json_list_keys():
    """Checkpoint round-trip stores checklist keys as lists, not tuples."""
    aching_key = ["aching", "symptom_quality", "pattern", "symptom_quality"]
    checklist = [
        _row("40", "demographic", "age"),
        _row("male", "demographic", "sex"),
        _row("pain", "ner_entity", "symptom", "gliner"),
        _row("aching pain", "ner_entity", "symptom", "gliner"),
        _row("aching", "symptom_quality", "symptom_quality"),
        _row("7 out of 10", "severity", "symptom_severity"),
        _row("gets worse when", "provocative", "provocative"),
    ]
    prior = {
        "s1": {
            "symptom_quality": [aching_key],
            "symptom_severity": [],
            "symptom_duration": [],
            "provocative": [],
            "palliative": [],
        },
        "s2": {
            "symptom_quality": [],
            "symptom_severity": [],
            "symptom_duration": [],
            "provocative": [],
            "palliative": [],
        },
    }
    report, assignments, _ = evaluate_checklist_coverage(
        checklist=checklist,
        comorbidities_acknowledged=True,
        symptom_slot_assignments=prior,
    )
    assert len(report["symptom_instances"]) >= 1
    assert assignments["s1"]["symptom_quality"]


def test_comorbidity_none_acknowledged():
    checklist = [_row("40", "demographic", "age"), _row("male", "demographic", "sex")]
    report, _, ack = evaluate_checklist_coverage(
        checklist=checklist,
        last_asked_slot="comorbidities",
        latest_user_message="none",
    )
    assert ack is True
    assert "comorbidities" not in {m["slot"] for m in report["missing_slots"]}


def test_gliner_hurts_plus_back_display_name():
    checklist = [
        _row("back", "ner_entity", "body part", "gliner"),
        _row("hurts", "ner_entity", "symptom", "gliner"),
    ]
    report, _, _ = evaluate_checklist_coverage(checklist=checklist)
    assert report["symptom_instances"][0]["display_name"] == "back pain"


def test_gliner_hurts_alone_becomes_pain():
    checklist = [_row("hurts", "ner_entity", "symptom", "gliner")]
    report, _, _ = evaluate_checklist_coverage(checklist=checklist)
    assert report["symptom_instances"][0]["display_name"] == "pain"


def test_consolidate_multiple_symptom_spans_to_one_instance():
    checklist = [
        _row("pain", "ner_entity", "symptom", "gliner"),
        _row("bruising", "ner_entity", "symptom", "gliner"),
        _row("tenderness", "ner_entity", "symptom", "gliner"),
    ]
    report, _, _ = evaluate_checklist_coverage(checklist=checklist)
    assert len(report["symptom_instances"]) == 1
    assert "pain" in report["symptom_instances"][0]["display_name"].casefold()


def test_gliner_symptom_duration_entity_satisfies_slot():
    checklist = [
        _row("low back pain", "ner_entity", "symptom", "gliner"),
        _row("yesterday", "ner_entity", "symptom duration", "gliner"),
    ]
    report, _, _ = evaluate_checklist_coverage(
        checklist=checklist, comorbidities_acknowledged=True
    )
    missing = {(m["slot"], m.get("symptom_id")) for m in report["missing_slots"]}
    assert ("symptom_duration", report["symptom_instances"][0]["symptom_id"]) not in missing

