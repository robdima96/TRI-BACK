"""Presentation adapter routing tests."""

import asyncio

from digimsk_study_app.adapters.base import ChatTurnResult
from digimsk_study_app.adapters.presentation import (
    PresentationAdapter,
    get_presentation_adapter,
    simplify_disposition,
)
from digimsk_study_app.graph import BotTraversalClient, reasoning_text
from digimsk_study_app.graph.schemas import GraphTraversalTrace, TraversalStep, ConditionTraversal
from digimsk_study_app.models.chat_types import filter_display_citations


def test_factory_returns_adapters_per_arm():
    assert get_presentation_adapter(1).group_id == 1
    assert get_presentation_adapter(2).group_id == 2
    assert get_presentation_adapter(3).group_id == 3
    assert get_presentation_adapter(99).group_id == 1


def test_simplify_disposition_keeps_short_text():
    text = "Please attend your nearest emergency department for assessment."
    assert simplify_disposition(text) == text


def test_simplify_disposition_trims_long_explanation():
    text = (
        "Please attend your nearest emergency department for assessment. "
        "This is because several red flags were present in the history. "
        "You should also bring a list of medications and prior imaging."
    )
    out = simplify_disposition(text)
    assert out.startswith("Please attend")
    assert "medications" not in out
    assert out.count(".") == 2


def test_reasoning_is_narrative_not_debug_dump():
    trace = GraphTraversalTrace(
        trace_id="t1",
        title="Test",
        matched_factors=["Severe pain", "Recent trauma"],
        candidate_conditions=["Fracture", "AAA"],
        shared_steps=[],
        condition_traversals=[
            ConditionTraversal(
                condition="Fracture",
                risk_score=26.5,
                rank=1,
                path_count=2,
                supporting_factors=["Severe pain", "Recent trauma"],
                steps=[
                    TraversalStep(
                        step=1,
                        action="evidence_link",
                        factor="Recent trauma",
                        condition="Fracture",
                        note="A recent history of trauma is a primary trigger for vertebral fracture.",
                    ),
                    TraversalStep(
                        step=2,
                        action="traverse_direct",
                        factor="Severe pain",
                        condition="Fracture",
                        relationship="ASSOCIATED_WITH",
                    ),
                    TraversalStep(
                        step=3,
                        action="match_chunk",
                        chunk_id="r_5",
                    ),
                ],
            ),
            ConditionTraversal(
                condition="AAA",
                risk_score=18.0,
                rank=2,
                path_count=1,
                supporting_factors=[],
                steps=[],
            ),
        ],
        steps=[],
    )
    text = reasoning_text(trace)
    assert "Severe pain" in text
    assert "Recent trauma" in text
    assert "Fracture" in text
    assert "AAA" in text
    assert "Checklist:" not in text
    assert "Evidence chunk:" not in text
    assert "Evidence cited:" not in text
    assert "graph:conditions" not in text
    assert "-[ASSOCIATED_WITH]->" not in text
    assert "risk score" not in text.lower()


def test_reasoning_omits_raw_checklist_dumps():
    trace = GraphTraversalTrace(
        trace_id="t1",
        title="Test",
        matched_factors=["Male sex"],
        candidate_conditions=["AAA"],
        shared_steps=[],
        condition_traversals=[],
        steps=[
            TraversalStep(
                step=1,
                action="checklist_item",
                checklist_item={"text": "exercise", "kind": "ner_entity"},
            ),
            TraversalStep(step=2, action="match_factor", factor="Male sex"),
            TraversalStep(
                step=3,
                action="unmatched",
                checklist_item={"text": "stiffness", "kind": "symptom_quality"},
            ),
        ],
    )
    text = reasoning_text(trace)
    assert "Checklist:" not in text
    assert "No factor match" not in text
    assert "Male sex" in text


def test_filter_display_citations_drops_debug_stubs():
    filtered = filter_display_citations(
        [
            {
                "source": "title: Red Flags Review",
                "snippet": "Trauma raises fracture concern.",
                "chunk_id": "r_5",
                "score": 0.9,
            },
            {
                "source": "factor:Severe pain",
                "snippet": "Checklist matched",
                "chunk_id": "",
                "score": 0.95,
            },
            {
                "source": "graph:conditions",
                "snippet": "Fracture, AAA",
                "chunk_id": "",
                "score": 0.8,
            },
            {
                "source": "r_5",
                "snippet": "dup",
                "chunk_id": "r_5",
                "score": 0.9,
            },
            {
                "source": "Female sex -[RISK_FACTOR_FOR]-> Fracture",
                "snippet": "path",
                "chunk_id": "r_4",
                "score": 1.0,
            },
        ]
    )
    assert len(filtered) == 1
    assert filtered[0]["chunk_id"] == "r_5"
    assert "title:" in filtered[0]["source"]


def test_traversal_client_parses_response():
    client = BotTraversalClient()
    result = ChatTurnResult(
        session_id="s1",
        response="ok",
        graph_traversal={
            "trace_id": "t1",
            "title": "x",
            "matched_factors": [],
            "candidate_conditions": [],
            "steps": [],
            "highlight": {"node_ids": [], "edge_ids": []},
            "nodes": [],
            "edges": [],
        },
    )
    trace = client.from_chat_response(result)
    assert trace is not None
    assert trace.trace_id == "t1"


def test_arm2_gets_reasoning_not_graph(monkeypatch):
    async def fake_chat(_session_id: str, _message: str) -> ChatTurnResult:
        return ChatTurnResult(
            session_id="s1",
            response="ok",
            citations=[
                {
                    "chunk_id": "r_1",
                    "source": "title: Example paper",
                    "snippet": "n",
                    "score": 0.8,
                },
                {
                    "chunk_id": "",
                    "source": "graph:conditions",
                    "snippet": "x",
                    "score": 0.5,
                },
            ],
            graph_traversal={
                "trace_id": "t1",
                "title": "Traversal",
                "matched_factors": ["Male sex"],
                "candidate_conditions": ["AAA"],
                "shared_steps": [
                    {"step": 1, "action": "match_factor", "factor": "Male sex"},
                ],
                "condition_traversals": [
                    {
                        "condition": "AAA",
                        "risk_score": 1.0,
                        "rank": 1,
                        "path_count": 1,
                        "supporting_factors": ["Male sex"],
                        "steps": [],
                        "nodes": [],
                        "edges": [],
                        "highlight": {"node_ids": [], "edge_ids": []},
                    }
                ],
                "steps": [],
                "highlight": {"node_ids": [], "edge_ids": []},
                "nodes": [],
                "edges": [],
            },
        )

    monkeypatch.setattr(
        "digimsk_study_app.adapters.presentation.call_chat_api",
        fake_chat,
    )
    result = asyncio.run(PresentationAdapter(2).send_message("s1", "hi"))
    assert result.reasoning_text
    assert "Male sex" in result.reasoning_text
    assert "Evidence cited:" not in result.reasoning_text
    assert result.graph_json is None
    assert result.has_graph is False
    assert all(c["source"] != "graph:conditions" for c in result.citations)


def test_arm1_simplifies_disposition_and_hides_extras(monkeypatch):
    async def fake_chat(_session_id: str, _message: str) -> ChatTurnResult:
        return ChatTurnResult(
            session_id="s1",
            response=(
                "Please attend your nearest emergency department now. "
                "Several red-flag factors raise concern for fracture. "
                "Bring prior imaging if available."
            ),
            coverage_ready=True,
            escalated=True,
            graph_traversal={
                "trace_id": "t1",
                "title": "Traversal",
                "matched_factors": ["Severe pain"],
                "candidate_conditions": ["Fracture"],
                "shared_steps": [],
                "condition_traversals": [],
                "steps": [],
                "highlight": {"node_ids": [], "edge_ids": []},
                "nodes": [],
                "edges": [],
            },
        )

    monkeypatch.setattr(
        "digimsk_study_app.adapters.presentation.call_chat_api",
        fake_chat,
    )
    result = asyncio.run(PresentationAdapter(1).send_message("s1", "hi"))
    assert result.reasoning_text is None
    assert result.has_graph is False
    assert "Bring prior imaging" not in result.response
    assert "emergency department" in result.response


def test_arm3_gets_graph_not_reasoning(monkeypatch):
    async def fake_chat(_session_id: str, _message: str) -> ChatTurnResult:
        return ChatTurnResult(
            session_id="s1",
            response="ok",
            graph_traversal={
                "trace_id": "t1",
                "title": "Traversal",
                "matched_factors": ["Male sex"],
                "candidate_conditions": ["AAA"],
                "shared_steps": [],
                "condition_traversals": [
                    {
                        "condition": "AAA",
                        "risk_score": 1.0,
                        "rank": 1,
                        "path_count": 1,
                        "supporting_factors": ["Male sex"],
                        "steps": [],
                        "nodes": [
                            {
                                "id": "n1",
                                "elementId": "n1",
                                "label": "Factor",
                                "name": "Male sex",
                            }
                        ],
                        "edges": [],
                        "highlight": {"node_ids": ["n1"], "edge_ids": []},
                    }
                ],
                "steps": [],
                "highlight": {"node_ids": [], "edge_ids": []},
                "nodes": [
                    {
                        "id": "n1",
                        "elementId": "n1",
                        "label": "Factor",
                        "name": "Male sex",
                    }
                ],
                "edges": [],
            },
        )

    monkeypatch.setattr(
        "digimsk_study_app.adapters.presentation.call_chat_api",
        fake_chat,
    )
    result = asyncio.run(PresentationAdapter(3).send_message("s1", "hi"))
    assert result.reasoning_text is None
    assert result.has_graph is True
    assert result.graph_json
