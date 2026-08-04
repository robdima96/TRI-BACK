import pytest
from langchain_core.messages import HumanMessage

from app.orchestrator.graph import build_chat_graph


def test_graph_generates_citations(monkeypatch: pytest.MonkeyPatch):
    """Encoder is absent in pytest; stub retrieval so the graph still returns citations."""

    import app.orchestrator.graph as graph_mod
    import app.orchestrator.nodes as nodes
    from app.schemas import ChunkMatch

    def _stub_chunks(
        query: str,
        query_embedding: list[float] | None,
        checklist,
        *,
        top_k: int | None = None,
        sub_collections=None,
    ) -> list[ChunkMatch]:
        return [
            ChunkMatch(
                chunk_id="pytest-1",
                source="pytest",
                snippet="Conservative care often includes activity as tolerated.",
                score=0.9,
                sub_collection="red_flags",
            )
        ]

    monkeypatch.setattr(
        "app.services.rag.chunk_retrieval.retrieve_rag_chunk_matches",
        _stub_chunks,
    )

    def _stub_plan(state):
        state["question_mode"] = False
        return state

    monkeypatch.setattr(nodes, "plan_question_node", _stub_plan)
    monkeypatch.setattr(graph_mod, "plan_question_node", _stub_plan)

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
