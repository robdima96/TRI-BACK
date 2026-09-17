"""Per-turn dedicated matcher owns factor_states; enricher does not emit Factors."""

from __future__ import annotations

import json
from unittest.mock import patch

from app.orchestrator.nodes import enrich_checklist_node
from app.orchestrator.question_planner import plan_next_question
from app.orchestrator.relevance_ranker import eligible_neighbour_factors
from app.services.agentic_graph_rag.ontology import load_ontology
from app.services.intake_enricher import (
    FactorStateUpdate,
    IntakeEnrichmentResult,
    apply_factor_state_updates,
    propose_checklist_enrichment,
)
from app.services.rag.factor_matcher import (
    affirmed_factor_names,
    checklist_row_deltas,
    drop_denied_factor_matches,
    match_checklist_to_factors,
)
from app.services.graphrag.schemas import FactorMatch
from app.schemas import ChecklistItem


def _coverage_for_planner():
    return {
        "session_complete": True,
        "symptoms_complete": False,
        "ready_for_disposition": False,
        "missing_slots": [
            {"slot": "provocative", "satisfied": False, "symptom_id": "s1"},
            {"slot": "palliative", "satisfied": False, "symptom_id": "s1"},
        ],
        "active_symptom_id": "s1",
        "symptom_instances": [
            {"symptom_id": "s1", "display_name": "back pain", "checklist_keys": []}
        ],
    }


def test_apply_unknown_does_not_clear_sticky_denied():
    prior = {"Saddle anaesthesia": "denied"}
    out = apply_factor_state_updates(
        prior,
        [FactorStateUpdate(factor="Saddle anaesthesia", polarity="unknown")],
    )
    assert out["Saddle anaesthesia"] == "denied"


def test_denied_factor_not_in_matched_factors():
    matches = [
        FactorMatch(
            checklist_item={"text": "tingling", "kind": "symptom", "source": "x", "label": "symptom"},
            factor_name="Neuro sensory deficit",
            match_method="pattern",
            match_score=1.0,
            polarity="affirmed",
        ),
        FactorMatch(
            checklist_item={"text": "weak", "kind": "symptom", "source": "x", "label": "symptom"},
            factor_name="Neuro motor deficit",
            match_method="pattern",
            match_score=1.0,
            polarity="affirmed",
        ),
    ]
    states = apply_factor_state_updates(
        {},
        [
            FactorStateUpdate(factor="Neuro motor deficit", polarity="affirmed"),
            FactorStateUpdate(factor="Neuro sensory deficit", polarity="denied"),
        ],
    )
    kept = drop_denied_factor_matches(matches, states)
    names = affirmed_factor_names(kept)
    assert "Neuro sensory deficit" not in names
    assert "Neuro motor deficit" in names


def test_checklist_row_deltas_by_id_and_signature():
    prior = [
        {"id": "cl_1", "text": "improved by", "kind": "palliative", "label": "palliative"},
        {"id": "cl_2", "text": "70", "kind": "demographic", "label": "age"},
    ]
    current = [
        {"id": "cl_1", "text": "Exercise helps", "kind": "palliative", "label": "palliative"},
        {"id": "cl_2", "text": "70", "kind": "demographic", "label": "age"},
        {"id": "cl_3", "text": "dull", "kind": "symptom_quality", "label": "symptom_quality"},
    ]
    deltas = checklist_row_deltas(prior, current)
    texts = {row["text"] for row in deltas}
    assert texts == {"Exercise helps", "dull"}


def test_enrich_node_runs_matcher_when_enricher_json_parsed():
    state = {
        "session_id": "sess-matcher-always",
        "message": "exercise",
        "message_normalized": "exercise",
        "turn_start_checklist": [],
        "clinical_checklist": [
            {
                "id": "cl_ex",
                "text": "exercise",
                "kind": "palliative",
                "source": "slot_answer",
                "label": "palliative",
            }
        ],
        "encoder_turn_items": [],
        "extraction_history": [],
        "messages": [],
        "asked_factor": None,
        "last_asked_slot": "palliative",
        "factor_states": {},
        "comorbidities_acknowledged": False,
    }
    with patch(
        "app.orchestrator.nodes.propose_checklist_enrichment",
        return_value=IntakeEnrichmentResult(
            status="no_changes",
            summary_reason="Palliative already on the checklist.",
        ),
    ):
        out = enrich_checklist_node(state)
    assert out["factor_states"].get("Improves with conservative care") == "affirmed"
    log = out["extraction_history"][0].get("factor_matching") or []
    assert any(row.get("factor_name") == "Improves with conservative care" for row in log)


def test_enrich_node_bare_no_denies_asked_factor_when_matcher_empty():
    asked = {
        "session_id": "sess-bare-no",
        "message": "no",
        "message_normalized": "no",
        "turn_start_checklist": [],
        "clinical_checklist": [],
        "encoder_turn_items": [],
        "extraction_history": [],
        "messages": [],
        "asked_factor": "Saddle anaesthesia",
        "last_asked_slot": None,
        "factor_states": {},
        "comorbidities_acknowledged": False,
    }
    with patch(
        "app.orchestrator.nodes.propose_checklist_enrichment",
        return_value=IntakeEnrichmentResult(
            status="no_changes",
            summary_reason="Nothing to add.",
        ),
    ):
        out = enrich_checklist_node(asked)
    assert out["factor_states"]["Saddle anaesthesia"] == "denied"
    assert not any(row.get("kind") == "palliative" for row in out["clinical_checklist"])


def test_enrich_node_falls_back_to_credit_when_enricher_unavailable():
    asked = {
        "session_id": "sess-fallback",
        "message": "no",
        "message_normalized": "no",
        "turn_start_checklist": [],
        "clinical_checklist": [],
        "encoder_turn_items": [],
        "extraction_history": [],
        "messages": [],
        "asked_factor": "Saddle anaesthesia",
        "last_asked_slot": None,
        "factor_states": {},
        "comorbidities_acknowledged": False,
    }
    with patch(
        "app.orchestrator.nodes.propose_checklist_enrichment",
        return_value=IntakeEnrichmentResult(
            status="unavailable",
            summary_reason="skipped",
        ),
    ):
        out = enrich_checklist_node(asked)
    assert out["factor_states"]["Saddle anaesthesia"] == "denied"


def test_denied_neighbours_skipped_after_matcher_and_credit():
    state = {
        "session_id": "sess-llm-factors",
        "message": "no",
        "message_normalized": "no",
        "turn_start_checklist": [],
        "clinical_checklist": [
            {
                "text": "weak",
                "kind": "ner_entity",
                "source": "gliner",
                "label": "symptom",
            }
        ],
        "encoder_turn_items": [],
        "extraction_history": [],
        "messages": [],
        "asked_factor": "Neuro sensory deficit",
        "last_asked_slot": None,
        "factor_states": {},
        "comorbidities_acknowledged": True,
    }
    motor = FactorMatch(
        checklist_item={
            "text": "weak",
            "kind": "ner_entity",
            "source": "gliner",
            "label": "symptom",
        },
        factor_name="Neuro motor deficit",
        match_method="regex",
        match_score=0.9,
        polarity="affirmed",
    )
    state["message"] = "no but my legs are weak"
    state["message_normalized"] = "no but my legs are weak"
    with patch(
        "app.orchestrator.nodes.propose_checklist_enrichment",
        return_value=IntakeEnrichmentResult(
            status="applied",
            summary_reason="Kept weakness row.",
        ),
    ), patch(
        "app.services.rag.factor_matcher.match_turn_to_factors",
        return_value=[motor],
    ):
        out = enrich_checklist_node(state)

    states = out["factor_states"]
    assert states["Neuro motor deficit"] == "affirmed"
    assert states["Neuro sensory deficit"] == "denied"

    neighbours = eligible_neighbour_factors(states, ontology=load_ontology())
    assert "Neuro sensory deficit" not in neighbours

    planned = plan_next_question(
        _coverage_for_planner(),
        risk_hits=[],
        questions_asked=5,
        comorbidities_acknowledged=True,
        factor_states=states,
        matched_factors=["Neuro motor deficit"],
    )
    assert planned.asked_factor != "Neuro sensory deficit"


def test_enrich_node_fills_provocative_na_from_llm_ops():
    state = {
        "session_id": "sess-na-slot",
        "message": "nothing",
        "message_normalized": "nothing",
        "turn_start_checklist": [],
        "clinical_checklist": [
            {
                "text": "low back pain",
                "kind": "ner_entity",
                "source": "gliner",
                "label": "symptom",
            }
        ],
        "encoder_turn_items": [],
        "extraction_history": [],
        "messages": [],
        "asked_factor": None,
        "last_asked_slot": "provocative",
        "factor_states": {},
        "comorbidities_acknowledged": True,
    }
    enrichment = IntakeEnrichmentResult(
        status="applied",
        summary_reason="Nothing aggravates the pain.",
        resulting_checklist=[
            {
                "text": "low back pain",
                "kind": "ner_entity",
                "source": "gliner",
                "label": "symptom",
            },
            {
                "text": "N/A",
                "kind": "provocative",
                "source": "llm",
                "label": "provocative",
            },
        ],
    )
    with patch(
        "app.orchestrator.nodes.propose_checklist_enrichment",
        return_value=enrichment,
    ):
        out = enrich_checklist_node(state)
    rows = [
        (row.get("kind"), row.get("text"))
        for row in out["clinical_checklist"]
    ]
    assert ("provocative", "N/A") in rows


@patch("app.services.intake_enricher.generate_from_messages")
@patch("app.services.intake_enricher.generator_model_configured", return_value=True)
def test_enrichment_prompt_omits_factor_inventory(mock_cfg, mock_gen):
    mock_gen.return_value = json.dumps(
        {
            "summary_reason": "No checklist changes.",
            "comorbidities_acknowledged": False,
            "checklist_operations": [],
            "next_intake": None,
        }
    )
    result = propose_checklist_enrichment(
        checklist=[
            {
                "text": "weak",
                "kind": "ner_entity",
                "source": "gliner",
                "label": "symptom",
            }
        ],
        latest_user_message="my legs are weak but I don't have any tingling",
        last_asked_factor="Neuro sensory deficit",
    )
    assert result.llm_ran is True
    prompt = mock_gen.call_args[0][0][0]["content"]
    assert "factor_matches" not in prompt
    assert "Inventory Factors" not in prompt
    assert "matching is not your job" in prompt.casefold() or "not your job" in prompt.casefold()
    assert "Last graph factor asked" in prompt
    assert "N/A" in prompt
    assert "Denials are not checklist rows" in prompt


def test_palliative_exercise_maps_to_conservative_care():
    items = [
        ChecklistItem(
            text="exercise",
            kind="palliative",
            source="slot_answer",
            label="palliative",
        )
    ]
    matches = match_checklist_to_factors(items, skip_llm=True)
    assert matches[0].factor_name == "Improves with conservative care"


def test_provocative_exercise_does_not_map_to_conservative_care():
    items = [
        ChecklistItem(
            text="exercise",
            kind="provocative",
            source="slot_answer",
            label="provocative",
        )
    ]
    matches = match_checklist_to_factors(items, skip_llm=True)
    assert matches[0].factor_name != "Improves with conservative care"
