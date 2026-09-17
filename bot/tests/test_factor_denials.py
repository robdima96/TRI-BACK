"""Denial-aware factor matching (Phase 1 adversarial fixtures)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import HumanMessage

from app.config import settings
from app.main import app
from app.orchestrator.graph import build_chat_graph
from app.schemas import ChecklistItem
from app.services.graphrag.orchestrator import traverse_from_turn
from app.services.rag.factor_matcher import (
    affirmed_factor_names,
    match_checklist_to_factors,
    merge_factor_states,
)
from app.session_store import session_file_path

client = TestClient(app)

# Actor denies every CES / DVT / infection red flag using the bot's own vocabulary.
DENIAL_FIXTURES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("no bladder problems", ("Bladder dysfunction",)),
    ("no numbness in the saddle area", ("Saddle anaesthesia",)),
    ("no bowel dysfunction", ("Bowel dysfunction",)),
    ("no calf pain or swelling", ("Calf pain", "Calf swelling")),
    ("no fever", ("Fever",)),
    ("no weight loss", ("Unexplained weight loss",)),
    ("no calf ache", ("Calf pain",)),
    ("no leg swelling", ("Calf swelling",)),
    ("denies bladder problems", ("Bladder dysfunction",)),
    ("never had bowel problems", ("Bowel dysfunction",)),
    ("haven't had any saddle numbness", ("Saddle anaesthesia",)),
    ("without any fever", ("Fever",)),
    ("nothing like saddle numbness", ("Saddle anaesthesia",)),
)


def _item(text: str) -> ChecklistItem:
    return ChecklistItem(text=text, kind="symptom", source="slot_answer", label="symptom")


def test_denial_fixtures_affirm_nothing_and_record_denied_states():
    all_matches = []
    states: dict[str, str] = {}
    expected_denied: set[str] = set()
    for text, factors in DENIAL_FIXTURES:
        expected_denied.update(factors)
        matches = match_checklist_to_factors([_item(text)], source_message=text)
        all_matches.extend(matches)
        states = merge_factor_states(states, matches)
        asserted = affirmed_factor_names(matches)
        assert asserted == [], f"{text!r} affirmed {asserted}"
        for factor in factors:
            assert states.get(factor) == "denied", (
                f"{text!r} did not deny {factor}; states={states}"
            )

    assert affirmed_factor_names(all_matches) == []
    for factor in expected_denied:
        assert states[factor] == "denied"


def test_denial_fixtures_do_not_seed_traversal_or_escalate():
    for text, factors in DENIAL_FIXTURES:
        trace = traverse_from_turn(
            checklist=[_item(text)],
            chunk_matches=[],
            trace_id="denial-fixture",
        )
        for factor in factors:
            assert factor not in trace.matched_factors, (
                f"{text!r} seeded traversal with {factor}"
            )
        assert "CES" not in trace.candidate_conditions
        assert "DVT" not in trace.candidate_conditions


@pytest.mark.parametrize(
    "text",
    [phrase for phrase, _ in DENIAL_FIXTURES],
)
def test_denial_phrases_do_not_escalate(text: str):
    graph = build_chat_graph()
    state = graph.invoke(
        {
            "session_id": "denial-escalate",
            "messages": [HumanMessage(content=text)],
        },
        {"configurable": {"thread_id": f"denial-escalate-{hash(text)}"}},
    )
    assert state.get("escalated") is False
    assert not affirmed_factor_names(
        match_checklist_to_factors([_item(text)], source_message=text)
    )
    for _phrase, factors in DENIAL_FIXTURES:
        if _phrase != text:
            continue
        for factor in factors:
            assert (state.get("factor_states") or {}).get(factor) == "denied"


def test_mixed_sentence_affirms_saddle_and_denies_bladder():
    text = "I have saddle numbness but no bladder problems"
    matches = match_checklist_to_factors([_item(text)], source_message=text)
    states = merge_factor_states({}, matches)
    assert "Saddle anaesthesia" in affirmed_factor_names(matches)
    assert states["Saddle anaesthesia"] == "affirmed"
    assert states["Bladder dysfunction"] == "denied"
    assert "Bladder dysfunction" not in affirmed_factor_names(matches)


def test_mixed_sentence_does_not_deny_back_pain_span():
    text = "my back is killing me but no bowel problems"
    matches = match_checklist_to_factors([_item(text)], source_message=text)
    states = merge_factor_states({}, matches)
    assert states.get("Bowel dysfunction") == "denied"
    assert "Bowel dysfunction" not in affirmed_factor_names(matches)
    for name in affirmed_factor_names(matches):
        assert name != "Bowel dysfunction"


def test_bare_bladder_without_cue_does_not_match():
    matches = match_checklist_to_factors([_item("my bladder")], source_message="my bladder")
    assert matches[0].factor_name is None
    assert merge_factor_states({}, matches) == {}


def test_bladder_issues_still_affirms():
    text = "bladder issues since Tuesday"
    matches = match_checklist_to_factors([_item(text)], source_message=text)
    assert "Bladder dysfunction" in affirmed_factor_names(matches)
    assert merge_factor_states({}, matches)["Bladder dysfunction"] == "affirmed"


def test_not_sure_stays_unknown():
    text = "I'm not sure if I have bladder problems"
    matches = match_checklist_to_factors([_item(text)], source_message=text)
    states = merge_factor_states({}, matches)
    assert "Bladder dysfunction" not in affirmed_factor_names(matches)
    assert states.get("Bladder dysfunction") != "denied"


def test_source_message_negation_rescues_stripped_entity():
    items = [_item("bladder problems")]
    matches = match_checklist_to_factors(
        items, source_message="no bladder problems"
    )
    assert affirmed_factor_names(matches) == []
    assert merge_factor_states({}, matches)["Bladder dysfunction"] == "denied"


def test_denials_are_sticky_until_affirm():
    denied = match_checklist_to_factors(
        [_item("no bladder problems")], source_message="no bladder problems"
    )
    states = merge_factor_states({}, denied)
    assert states["Bladder dysfunction"] == "denied"
    idle = match_checklist_to_factors([_item("the pain is still there")])
    states = merge_factor_states(states, idle)
    assert states["Bladder dysfunction"] == "denied"
    affirmed = match_checklist_to_factors(
        [_item("I can't control my bladder")],
        source_message="I can't control my bladder",
    )
    states = merge_factor_states(states, affirmed)
    assert states["Bladder dysfunction"] == "affirmed"


def test_unknown_is_sticky_until_affirm():
    states = merge_factor_states(
        {"Saddle anaesthesia": "unknown"},
        match_checklist_to_factors([_item("the pain is still there")]),
    )
    assert states["Saddle anaesthesia"] == "unknown"
    affirmed = match_checklist_to_factors(
        [_item("I have saddle numbness")],
        source_message="I have saddle numbness",
    )
    states = merge_factor_states(states, affirmed)
    assert states["Saddle anaesthesia"] == "affirmed"


def test_factor_states_round_trip_checkpointer():
    graph = build_chat_graph()
    cfg = {"configurable": {"thread_id": "factor-states-rt"}}
    graph.invoke(
        {
            "session_id": "factor-states-rt",
            "messages": [HumanMessage(content="no bladder problems")],
        },
        cfg,
    )
    s1 = graph.get_state(cfg)
    assert (s1.values.get("factor_states") or {}).get("Bladder dysfunction") == "denied"

    graph.invoke(
        {
            "session_id": "factor-states-rt",
            "messages": [HumanMessage(content="I'm 42")],
        },
        cfg,
    )
    s2 = graph.get_state(cfg)
    assert (s2.values.get("factor_states") or {}).get("Bladder dysfunction") == "denied"


def test_factor_states_appear_in_session_json():
    sid = "sess-factor-states-1"
    r = client.post(
        "/api/v1/chat",
        json={"session_id": sid, "message": "no bowel dysfunction"},
    )
    assert r.status_code == 200
    assert r.json()["escalated"] is False
    path = session_file_path(sid, root=Path(settings.session_store_dir))
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["factor_states"]["Bowel dysfunction"] == "denied"
    assert data["orchestrator"]["factor_states"]["Bowel dysfunction"] == "denied"
    assert "Bowel dysfunction" not in (data.get("matched_factors") or [])
