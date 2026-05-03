from langgraph.graph import END, START, StateGraph

from app.orchestrator.nodes import (
    encode_input_node,
    finalize_response_node,
    generate_draft_node,
    ingest_input_node,
    policy_gate_node,
    preprocess_input_node,
    retrieve_evidence_node,
)
from app.orchestrator.state import ChatState


def build_chat_graph(checkpointer=None):
    if checkpointer is None:
        from langgraph.checkpoint.memory import MemorySaver
        checkpointer = MemorySaver()
        
    graph = StateGraph(ChatState)
    graph.add_node("preprocess_input", preprocess_input_node)
    graph.add_node("ingest_input", ingest_input_node)
    graph.add_node("encode_input", encode_input_node)
    graph.add_node("retrieve_evidence", retrieve_evidence_node)
    graph.add_node("generate_draft", generate_draft_node)
    graph.add_node("policy_gate", policy_gate_node)
    graph.add_node("finalize_response", finalize_response_node)

    graph.add_edge(START, "preprocess_input")
    graph.add_edge("preprocess_input", "ingest_input")
    graph.add_edge("ingest_input", "encode_input")
    graph.add_edge("encode_input", "retrieve_evidence")
    graph.add_edge("retrieve_evidence", "generate_draft")
    graph.add_edge("generate_draft", "policy_gate")
    graph.add_edge("policy_gate", "finalize_response")
    graph.add_edge("finalize_response", END)

    return graph.compile(checkpointer=checkpointer)
