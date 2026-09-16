"""Session triage profile: assumed LBP chief complaint and pack paths."""

from dataclasses import replace

from app.orchestrator.coverage import evaluate_checklist_coverage
from app.orchestrator.intake_slots import question_template
from app.orchestrator.nodes import ingest_input_node
from app.orchestrator.question_planner import plan_next_question
from app.services.agentic_graph_rag.ontology import load_ontology
from app.services.graphrag.local_graph import get_graph_client
from app.services.graphrag.neo4j_config import (
    DEFAULT_CSV_PATH,
    DEFAULT_FACTORS_PATH,
    DEFAULT_INVENTORY_PATH,
)
from app.services.intake_enricher import _next_intake_slot_rules
from app.triage_profiles import (
    DEFAULT_PROFILE_ID,
    LOW_BACK_INTRO_MESSAGE,
    PROFILE_SYMPTOM_SOURCE,
    bind_triage_profile,
    get_triage_profile,
    graph_client_for_profile,
    load_ontology_for_profile,
    seed_profile_symptom,
)


def _row(text: str, kind: str, label: str, source: str = "pattern") -> dict[str, str]:
    return {"text": text, "kind": kind, "source": source, "label": label}


def test_low_back_is_the_default_profile():
    profile = get_triage_profile()
    assert profile.id == DEFAULT_PROFILE_ID
    assert profile.symptom_text == "low back pain"
    assert profile.assumes_symptom is True
    assert profile.intro_message == LOW_BACK_INTRO_MESSAGE
    assert "concerning patterns" in profile.intro_message
    assert profile.graph_csv == DEFAULT_CSV_PATH
    assert profile.graph_factors == DEFAULT_FACTORS_PATH
    assert profile.graph_inventory == DEFAULT_INVENTORY_PATH


def test_unknown_profile_id_falls_back_to_low_back():
    assert get_triage_profile("knee").id == DEFAULT_PROFILE_ID


def test_bind_stamps_first_turn_and_ignores_later_request():
    state: dict = {"requested_triage_profile_id": "low_back"}
    first = bind_triage_profile(state)
    assert first.id == "low_back"
    assert state["triage_profile_id"] == "low_back"

    state["requested_triage_profile_id"] = "knee"
    second = bind_triage_profile(state)
    assert second.id == "low_back"
    assert state["triage_profile_id"] == "low_back"


def test_ingest_seeds_profile_symptom_before_any_user_span():
    state: dict = {"clinical_checklist": []}
    ingest_input_node(state)
    rows = state["clinical_checklist"]
    assert any(
        r.get("source") == PROFILE_SYMPTOM_SOURCE
        and r.get("label") == "symptom"
        and r.get("text") == "low back pain"
        for r in rows
    )
    report, _, _ = evaluate_checklist_coverage(checklist=rows)
    missing = {m["slot"] for m in report["missing_slots"]}
    assert "symptom_anchor" not in missing
    assert report["symptom_instances"][0]["display_name"] == "low back pain"


def test_seed_is_idempotent():
    state: dict = {"triage_profile_id": "low_back", "clinical_checklist": []}
    seed_profile_symptom(state)
    seed_profile_symptom(state)
    seeds = [
        r
        for r in state["clinical_checklist"]
        if r.get("source") == PROFILE_SYMPTOM_SOURCE
    ]
    assert len(seeds) == 1


def test_unassumed_profile_does_not_seed_symptom(monkeypatch):
    bare = replace(get_triage_profile(), symptom_text="")
    assert bare.assumes_symptom is False
    monkeypatch.setattr(
        "app.triage_profiles.get_triage_profile", lambda _id=None: bare
    )
    state: dict = {"triage_profile_id": "bare", "clinical_checklist": []}
    seed_profile_symptom(state)
    assert state["clinical_checklist"] == []


def test_profile_display_name_stays_sticky_with_extra_symptom_spans():
    checklist = [
        _row("low back pain", "ner_entity", "symptom", PROFILE_SYMPTOM_SOURCE),
        _row("sciatica", "ner_entity", "symptom", "gliner"),
        _row("stiffness", "ner_entity", "symptom", "gliner"),
    ]
    report, _, _ = evaluate_checklist_coverage(checklist=checklist)
    assert len(report["symptom_instances"]) == 1
    assert report["symptom_instances"][0]["display_name"] == "low back pain"


def test_seeded_planner_skips_symptom_anchor():
    state: dict = {"clinical_checklist": []}
    ingest_input_node(state)
    report, _, _ = evaluate_checklist_coverage(
        checklist=state["clinical_checklist"],
        preferred_body_parts=get_triage_profile().preferred_body_parts,
    )
    planned = plan_next_question(
        report,
        risk_hits=[],
        questions_asked=0,
        comorbidities_acknowledged=False,
        profile=get_triage_profile(),
    )
    assert planned.question_mode is True
    assert planned.slot != "symptom_anchor"
    assert planned.question_reason is None or "rank:t0:symptom_anchor" not in (
        planned.question_reason or ""
    )
    assert planned.slot == "age"


def test_quality_template_uses_low_back_pain_display_name():
    checklist = [
        _row("low back pain", "ner_entity", "symptom", PROFILE_SYMPTOM_SOURCE),
        _row("40", "demographic", "age"),
        _row("female", "demographic", "sex"),
    ]
    report, _, _ = evaluate_checklist_coverage(
        checklist=checklist,
        comorbidities_acknowledged=True,
    )
    planned = plan_next_question(
        report,
        risk_hits=[],
        questions_asked=3,
        comorbidities_acknowledged=True,
        profile=get_triage_profile(),
    )
    assert planned.slot == "symptom_quality"
    assert planned.next_question == question_template(
        "symptom_quality", display_name="low back pain"
    )
    assert "low back pain" in (planned.next_question or "")


def test_pack_helpers_thread_profile_paths():
    profile = get_triage_profile()
    ont = load_ontology_for_profile(profile)
    via_paths = load_ontology(
        csv_path=profile.graph_csv,
        factors_path=profile.graph_factors,
        inventory_path=profile.graph_inventory,
    )
    assert ont is via_paths
    client = graph_client_for_profile(profile)
    assert client is get_graph_client(csv_path=profile.graph_csv)


def test_enricher_hint_skips_anchor_when_complaint_is_assumed():
    rules = _next_intake_slot_rules(get_triage_profile())
    assert "already assumed" in rules
    assert "symptom_anchor →" not in rules
    assert "low back pain" in rules
    bare = replace(get_triage_profile(), symptom_text="")
    fallback = _next_intake_slot_rules(bare)
    assert "symptom_anchor →" in fallback
