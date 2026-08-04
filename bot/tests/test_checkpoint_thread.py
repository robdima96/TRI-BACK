"""LangGraph checkpointer carries ``messages`` across invokes (same thread_id)."""

from langchain_core.messages import AIMessage, HumanMessage

from app.orchestrator.graph import build_chat_graph


def test_checkpoint_thread_accumulates_messages():
    graph = build_chat_graph()
    cfg = {"configurable": {"thread_id": "thread-mt-checkpoint"}}

    graph.invoke(
        {
            "session_id": "thread-mt-checkpoint",
            "messages": [HumanMessage(content="First turn.")],
        },
        cfg,
    )
    s1 = graph.get_state(cfg)
    assert len(s1.values["messages"]) == 2
    assert isinstance(s1.values["messages"][0], HumanMessage)
    assert isinstance(s1.values["messages"][1], AIMessage)

    graph.invoke(
        {
            "session_id": "thread-mt-checkpoint",
            "messages": [HumanMessage(content="Second turn.")],
        },
        cfg,
    )
    s2 = graph.get_state(cfg)
    assert len(s2.values["messages"]) == 4
