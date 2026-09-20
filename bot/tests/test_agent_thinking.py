"""Agentic generate_from_messages thinking / JSON mime kwargs."""

from __future__ import annotations

from unittest.mock import patch

from app.services.agentic_graph_rag.agent import run_disposition_agent
from app.services.agentic_graph_rag.ontology import RedFlagOntology


def _ontology() -> RedFlagOntology:
    return RedFlagOntology(
        graph_version="test",
        conditions=("Fracture",),
        factors_by_condition={"Fracture": ("Recent trauma",)},
        mediators=(),
        relations=("RISK_FACTOR_FOR",),
        all_factors=("Recent trauma",),
    )


@patch("app.services.generator.generate_from_messages")
def test_agent_generate_calls_use_medium_thinking_and_json_mime(mock_gen):
    mock_gen.return_value = '{"final_answer": "Please seek urgent care."}'
    text, _trace = run_disposition_agent(
        query="back pain after a fall",
        checklist=[],
        chunk_matches=[],
        ontology=_ontology(),
        matched_factors=["Recent trauma"],
        touched_conditions=[],
        baseline_evidence=[],
        intake_summary=None,
        conversation_history=None,
        max_steps=2,
    )
    assert text
    assert mock_gen.call_count >= 1
    for call in mock_gen.call_args_list:
        assert call.kwargs["thinking_level"] == "MEDIUM"
        assert call.kwargs["response_mime_type"] == "application/json"


@patch("app.services.generator.generate_from_messages")
def test_agent_forced_final_without_final_answer_returns_none(mock_gen):
    mock_gen.return_value = '{"thought": "need a tool", "action": "get_matched_factors"}'
    text, trace = run_disposition_agent(
        query="back pain after a fall",
        checklist=[],
        chunk_matches=[],
        ontology=_ontology(),
        matched_factors=["Recent trauma"],
        touched_conditions=[],
        baseline_evidence=[],
        intake_summary=None,
        conversation_history=None,
        max_steps=1,
    )
    assert text is None
    assert trace.stop_reason == "no_final_after_budget"
    assert "{" not in (text or "")
