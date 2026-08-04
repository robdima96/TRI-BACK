"""Graph intake path: question turn vs disposition turn."""

import pytest
from langchain_core.messages import HumanMessage

from app.orchestrator.graph import build_chat_graph


def test_first_turn_asks_intake_question():
    graph = build_chat_graph()
    state = graph.invoke(
        {
            "session_id": "intake-001",
            "messages": [HumanMessage(content="I have low back pain.")],
        },
        {"configurable": {"thread_id": "intake-001"}},
    )
    assert state.get("question_mode") is True
    assert state.get("questions_asked", 0) >= 1
    assert state["final_response"]
    assert not state.get("coverage", {}).get("ready_for_disposition")
    assert state["evidence"] == []
