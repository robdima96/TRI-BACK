import pytest
from langchain_core.messages import HumanMessage

from app.orchestrator.graph import build_chat_graph
from app.schemas import Evidence


def test_graph_generates_citations(monkeypatch: pytest.MonkeyPatch):
    """Encoder is absent in pytest; stub retrieval so the graph still returns citations."""

    import app.orchestrator.nodes as nodes

    def _stub_retrieve(
        query: str, query_embedding: list[float], top_k: int | None = None
    ) -> list[Evidence]:
        return [
            Evidence(
                source="pytest",
                snippet="Conservative care often includes activity as tolerated.",
                score=0.9,
            )
        ]

    monkeypatch.setattr(nodes, "retrieve_evidence", _stub_retrieve)

    graph = build_chat_graph()
    state = graph.invoke(
        {
            "session_id": "s-003",
            "messages": [
                HumanMessage(
                    content="What is conservative management for back pain?"
                )
            ],
        },
        {"configurable": {"thread_id": "s-003"}},
    )
    assert len(state["evidence"]) > 0
    assert state["final_response"]


def test_policy_gate_blocks_unsafe_output():
    graph = build_chat_graph()
    state = graph.invoke(
        {
            "session_id": "s-004",
            "messages": [
                HumanMessage(content="I have suicide thoughts and severe chest pain.")
            ],
        },
        {"configurable": {"thread_id": "s-004"}},
    )
    assert state["escalated"] is True
