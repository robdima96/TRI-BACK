"""LLM-owned graph Factor matching via the intake enricher."""

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
    parse_factor_matches,
    propose_checklist_enrichment,
)
from app.services.rag.factor_matcher import (
    affirmed_factor_names,
    drop_denied_factor_matches,
)
from app.services.graphrag.schemas import FactorMatch


_INVENTORY = (
    "Neuro motor deficit",
    "Neuro sensory deficit",
    "Bilat neuro sensory deficit",
    "Bilat neuro motor deficit",
    "Saddle anaesthesia",
)


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


def test_parse_factor_matches_keeps_inventory_names_and_drops_unknown():
    accepted, rejected = parse_factor_matches(
        {
            "factor_matches": [
                {
                    "factor": "Neuro motor deficit",
                    "polarity": "affirmed",
                    "reason": "legs weak",
                },
                {
                    "factor": "Neuro sensory deficit",
                    "polarity": "denied",
                    "reason": "no tingling",
                },
                {
                    "factor": "Bilat neuro sensory deficit",
                    "polarity": "denied",
                    "reason": "cannot be both legs",
                },
                {"factor": "Not A Real Factor", "polarity": "affirmed"},
                {"factor": "Saddle anaesthesia", "polarity": "maybe"},
            ]
        },
        inventory=_INVENTORY,
    )
    names = {item.factor: item.polarity for item in accepted}
    assert names["Neuro motor deficit"] == "affirmed"
    assert names["Neuro sensory deficit"] == "denied"
    assert names["Bilat neuro sensory deficit"] == "denied"
    assert "Not A Real Factor" not in names
    assert "Saddle anaesthesia" not in names
    assert rejected == 2


def test_parse_factor_matches_later_row_wins():
    accepted, rejected = parse_factor_matches(
        {
            "factor_matches": [
                {"factor": "Neuro motor deficit", "polarity": "denied"},
                {"factor": "neuro motor deficit", "polarity": "affirmed"},
            ]
        },
        inventory=_INVENTORY,
    )
    assert rejected == 0
    assert len(accepted) == 1
    assert accepted[0].factor == "Neuro motor deficit"
    assert accepted[0].polarity == "affirmed"


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


def test_enrich_node_applies_llm_factor_matches_without_regex():
    state = {
        "session_id": "sess-llm-factors",
        "message": "my legs are weak but I don't have any tingling",
        "message_normalized": "my legs are weak but I don't have any tingling",
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
    enrichment = IntakeEnrichmentResult(
        status="applied",
        summary_reason="Mixed motor affirm and sensory deny.",
        factor_matches=[
            FactorStateUpdate(factor="Neuro motor deficit", polarity="affirmed"),
            FactorStateUpdate(factor="Neuro sensory deficit", polarity="denied"),
            FactorStateUpdate(
                factor="Bilat neuro sensory deficit", polarity="denied"
            ),
        ],
    )
    with patch(
        "app.orchestrator.nodes.propose_checklist_enrichment",
        return_value=enrichment,
    ):
        out = enrich_checklist_node(state)

    states = out["factor_states"]
    assert states["Neuro motor deficit"] == "affirmed"
    assert states["Neuro sensory deficit"] == "denied"
    assert states["Bilat neuro sensory deficit"] == "denied"
    log = out["extraction_history"][0]["llm_enrichment"]
    assert len(log["factor_matches"]) == 3

    neighbours = eligible_neighbour_factors(states, ontology=load_ontology())
    assert "Neuro sensory deficit" not in neighbours
    assert "Bilat neuro sensory deficit" not in neighbours

    planned = plan_next_question(
        _coverage_for_planner(),
        risk_hits=[],
        questions_asked=5,
        comorbidities_acknowledged=True,
        factor_states=states,
        matched_factors=["Neuro motor deficit"],
    )
    assert planned.asked_factor != "Neuro sensory deficit"
    assert planned.asked_factor != "Bilat neuro sensory deficit"


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


def test_enrich_node_skips_regex_matcher_when_llm_ran():
    state = {
        "session_id": "sess-skip-regex",
        "message": "aching",
        "message_normalized": "aching",
        "turn_start_checklist": [],
        "clinical_checklist": [
            {
                "text": "aching",
                "kind": "symptom_quality",
                "source": "pattern",
                "label": "symptom_quality",
            }
        ],
        "encoder_turn_items": [],
        "extraction_history": [],
        "messages": [],
        "asked_factor": None,
        "last_asked_slot": "symptom_quality",
        "factor_states": {},
        "comorbidities_acknowledged": False,
    }
    with patch(
        "app.orchestrator.nodes.propose_checklist_enrichment",
        return_value=IntakeEnrichmentResult(
            status="no_changes",
            summary_reason="Quality already on the checklist.",
        ),
    ), patch(
        "app.services.rag.factor_matcher.update_factor_states_from_checklist"
    ) as matcher:
        out = enrich_checklist_node(state)
    matcher.assert_not_called()
    assert out["factor_states"] == {}


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


@patch("app.services.intake_enricher.generate_from_messages")
@patch("app.services.intake_enricher.generator_model_configured", return_value=True)
def test_enrichment_parses_factor_matches_from_json(mock_cfg, mock_gen):
    mock_gen.return_value = json.dumps(
        {
            "summary_reason": "Motor yes, sensory no.",
            "comorbidities_acknowledged": False,
            "checklist_operations": [],
            "factor_matches": [
                {"factor": "Neuro motor deficit", "polarity": "affirmed"},
                {"factor": "Neuro sensory deficit", "polarity": "denied"},
                {"factor": "Bilat neuro sensory deficit", "polarity": "denied"},
                {"factor": "Invented Factor", "polarity": "affirmed"},
            ],
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
        inventory=_INVENTORY,
    )
    assert result.llm_ran is True
    names = {item.factor: item.polarity for item in result.factor_matches}
    assert names["Neuro motor deficit"] == "affirmed"
    assert names["Neuro sensory deficit"] == "denied"
    assert names["Bilat neuro sensory deficit"] == "denied"
    assert "Invented Factor" not in names
    prompt = mock_gen.call_args[0][0][0]["content"]
    assert "factor_matches" in prompt
    assert "Inventory Factors" in prompt
    assert "N/A" in prompt
