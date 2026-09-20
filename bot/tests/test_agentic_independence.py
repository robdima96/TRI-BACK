"""Agentic/deterministic disposition independence contracts."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.config import settings
from app.orchestrator.graph import _disposition_entry
from app.services.agentic_graph_rag.ontology import (
    RedFlagOntology,
    tally_touched_conditions,
)
from app.services.agentic_graph_rag.prompt_template import render_system_prompt
from app.services.agentic_graph_rag.schemas import AgentTrace
from app.services.agentic_graph_rag.tools import tool_names
from app.services.graphrag.inference import (
    BayesianNotConfiguredError,
    get_condition_scorer,
)
from app.services.graphrag.schemas import GraphTraversalTrace


def _ontology() -> RedFlagOntology:
    return RedFlagOntology(
        graph_version="test",
        conditions=("Fracture", "Infection", "Non-specific Mechanical Cause"),
        factors_by_condition={
            "Fracture": ("Recent trauma", "Severe pain"),
            "Infection": ("Fever", "Severe pain"),
            "Non-specific Mechanical Cause": ("Movement-related pain",),
        },
        mediators=(),
        relations=("RISK_FACTOR_FOR",),
        all_factors=(
            "Recent trauma",
            "Severe pain",
            "Fever",
            "Movement-related pain",
        ),
    )


def test_touched_conditions_is_membership_tally_not_risk_score():
    touched = tally_touched_conditions(["Severe pain", "Recent trauma"], _ontology())
    assert touched == [
        {
            "condition": "Fracture",
            "factor_hit_count": 2,
            "matched_factors": ["Recent trauma", "Severe pain"],
        },
        {
            "condition": "Infection",
            "factor_hit_count": 1,
            "matched_factors": ["Severe pain"],
        },
    ]
    assert all("risk_score" not in row for row in touched)


def test_agentic_routing_does_not_require_graphrag(monkeypatch):
    monkeypatch.setattr(settings, "disposition_mode", "agentic")
    monkeypatch.setattr(settings, "graphrag_load", False)
    assert _disposition_entry() == "agentic_disposition"


def test_rag_only_agent_catalog_keeps_tally_and_search(monkeypatch):
    monkeypatch.setattr(settings, "rag_load", True)
    monkeypatch.setattr(settings, "graphrag_load", False)
    monkeypatch.setattr(settings, "agentic_bayesian_tool", False)
    names = tool_names()
    assert "get_matched_factors" in names
    assert "list_touched_conditions" in names
    assert "search_evidence" in names
    assert "get_factor_paths" not in names
    assert "get_condition_evidence" not in names
    assert "score_conditions_bayesian" not in names


def test_prompt_selects_traditional_rag_framework_when_graph_disabled():
    prompt = render_system_prompt(
        ontology=_ontology(),
        matched_factors=["Severe pain"],
        touched_conditions=[
            {
                "condition": "Fracture",
                "factor_hit_count": 1,
                "matched_factors": ["Severe pain"],
            }
        ],
        intake_summary="Intake complete.",
        evidence=[],
        max_steps=3,
        graph_enabled=False,
    )
    assert "Graph traversal is disabled for this run" in prompt
    assert "not probabilities, risk scores, or a ranking" in prompt
    assert "deterministic ground-truth ranking" not in prompt


def test_bayesian_scorer_is_explicit_unconfigured_skeleton():
    scorer = get_condition_scorer("bayesian")
    with pytest.raises(BayesianNotConfiguredError, match="priors/CPTs"):
        scorer.score([])


def test_agentic_node_does_not_pre_run_deterministic_traversal(monkeypatch):
    from app.services.agentic_graph_rag.node import agentic_disposition_node

    monkeypatch.setattr(settings, "rag_load", False)
    monkeypatch.setattr(settings, "graphrag_load", True)
    monkeypatch.setattr(settings, "agentic_max_steps", 2)

    trace = AgentTrace(
        status="ok",
        stop_reason="final_answer",
        max_steps=2,
        steps_taken=1,
    )
    state = {
        "message_normalized": "low back pain",
        "clinical_checklist": [],
        "coverage": {},
        "messages": [],
        "session_id": "test_1",
    }
    with (
        patch(
            "app.services.generator.generator_model_configured",
            return_value=True,
        ),
        patch(
            "app.services.agentic_graph_rag.agent.run_disposition_agent",
            return_value=("Self-care with monitoring.", trace),
        ) as run_agent,
        patch(
            "app.services.graphrag.orchestrator.traverse_from_turn",
            side_effect=AssertionError("deterministic traversal ran before agent"),
        ),
    ):
        result = agentic_disposition_node(state)

    assert result["draft_response"] == "Self-care with monitoring."
    assert result["candidate_conditions"] == []
    assert result["agent_trace"]["fallback_used"] is False
    assert "touched_conditions" in run_agent.call_args.kwargs
    assert "deterministic_conditions" not in run_agent.call_args.kwargs


def test_agentic_success_without_graph_conditions_stays_schema_valid(monkeypatch):
    """Study Arm-2/Arm-3 clients drop payloads that fail trace validation."""
    from app.services.agentic_graph_rag.node import agentic_disposition_node
    from app.services.graphrag.schemas import GraphTraversalTrace as BotTrace

    monkeypatch.setattr(settings, "rag_load", True)
    monkeypatch.setattr(settings, "graphrag_load", False)
    monkeypatch.setattr(settings, "agentic_max_steps", 2)
    trace = AgentTrace(status="ok", stop_reason="final_answer", max_steps=2)
    state = {
        "message_normalized": "aching back after gardening",
        "clinical_checklist": [],
        "coverage": {},
        "messages": [],
        "session_id": "test_4",
    }
    with (
        patch(
            "app.services.generator.generator_model_configured",
            return_value=True,
        ),
        patch(
            "app.services.rag.chunk_retrieval.retrieve_rag_chunk_matches",
            return_value=[],
        ),
        patch(
            "app.services.agentic_graph_rag.agent.run_disposition_agent",
            return_value=("Self-care with monitoring.", trace),
        ),
    ):
        result = agentic_disposition_node(state)

    payload = result["graph_traversal"]
    assert payload["inference"] == "agentic_no_graph_conditions"
    assert BotTrace.model_validate(payload).condition_traversals == []


def test_agentic_failure_runs_clearly_logged_deterministic_fallback(monkeypatch):
    from app.services.agentic_graph_rag.node import agentic_disposition_node

    monkeypatch.setattr(settings, "rag_load", False)
    monkeypatch.setattr(settings, "graphrag_load", True)
    monkeypatch.setattr(settings, "agentic_max_steps", 2)
    failed = AgentTrace(
        status="fallback",
        stop_reason="unparseable_output",
        max_steps=2,
    )
    deterministic = GraphTraversalTrace(
        trace_id="fallback-1",
        title="fallback",
        candidate_conditions=["Fracture"],
    )
    state = {
        "message_normalized": "low back pain",
        "clinical_checklist": [],
        "coverage": {},
        "messages": [],
        "session_id": "test_2",
    }
    with (
        patch(
            "app.services.generator.generator_model_configured",
            return_value=True,
        ),
        patch(
            "app.services.agentic_graph_rag.agent.run_disposition_agent",
            return_value=(None, failed),
        ),
        patch(
            "app.services.graphrag.traverse_from_turn",
            return_value=deterministic,
        ) as traverse,
        patch(
            "app.services.generator.generate_response_result",
            return_value=("Deterministic fallback response.", None),
        ),
    ):
        result = agentic_disposition_node(state)

    traverse.assert_called_once()
    assert result["draft_response"] == "Deterministic fallback response."
    assert result["agent_trace"]["fallback_used"] is True
    assert result["agent_trace"]["fallback_mode"] == "deterministic"
    assert result["graph_traversal"]["inference"] == "deterministic_fallback"


def test_agentic_success_builds_arm3_payload_after_agent(monkeypatch):
    from app.services.agentic_graph_rag.node import agentic_disposition_node

    monkeypatch.setattr(settings, "rag_load", False)
    monkeypatch.setattr(settings, "graphrag_load", True)
    monkeypatch.setattr(settings, "agentic_max_steps", 2)
    agent_trace = AgentTrace(
        status="ok",
        stop_reason="final_answer",
        max_steps=2,
        steps_taken=2,
        used_factors=["Recent trauma"],
        used_conditions=["Fracture"],
    )
    provenance = GraphTraversalTrace(
        trace_id="agentic-1",
        title="agentic provenance",
        matched_factors=["Recent trauma"],
        candidate_conditions=["Fracture"],
    )
    state = {
        "message_normalized": "fell from a ladder",
        "clinical_checklist": [],
        "coverage": {},
        "messages": [],
        "session_id": "test_3",
    }
    with (
        patch(
            "app.services.generator.generator_model_configured",
            return_value=True,
        ),
        patch(
            "app.services.agentic_graph_rag.agent.run_disposition_agent",
            return_value=("Urgent in-person assessment.", agent_trace),
        ),
        patch(
            "app.services.graphrag.condition_traversals.build_agent_provenance_trace",
            return_value=provenance,
        ) as build_payload,
        patch(
            "app.services.graphrag.orchestrator.traverse_from_turn",
            side_effect=AssertionError("pre-agent deterministic traversal ran"),
        ),
    ):
        result = agentic_disposition_node(state)

    build_payload.assert_called_once()
    assert result["candidate_conditions"] == ["Fracture"]
    assert result["graph_traversal"]["candidate_conditions"] == ["Fracture"]
    assert (
        result["graph_traversal"]["inference"]
        == "agentic_provenance_unscored"
    )
