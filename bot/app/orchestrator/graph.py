from langgraph.graph import END, START, StateGraph

from app.orchestrator.nodes import (
    encode_input_node,
    enrich_checklist_node,
    evaluate_coverage_node,
    finalize_response_node,
    generate_draft_node,
    generate_question_node,
    ingest_input_node,
    plan_question_node,
    policy_gate_node,
    preprocess_input_node,
    retrieve_evidence_node,
    graph_traversal_node,
)
from app.orchestrator.state import ChatState


def _agentic_disposition_node(state: ChatState) -> ChatState:
    """Lazy wrapper so the agentic package is only imported when the graph builds."""
    from app.services.agentic_graph_rag import agentic_disposition_node

    return agentic_disposition_node(state)


def _disposition_entry() -> str:
    """First disposition node: deterministic chain vs agentic (toggle).

    Evidence-path toggles are independent of disposition reasoning style.
    """
    from app.config import settings

    if settings.disposition_mode == "agentic":
        return "agentic_disposition"
    return "retrieve_evidence"


def _route_after_encode(state: ChatState) -> str:
    """Skip intake LLM work when a hard risk pattern already fired."""
    if state.get("risk_hits"):
        return "policy_gate"
    return "enrich_checklist"


def _route_after_plan(state: ChatState) -> str:
    """Risk escalation, intake question, or disposition (RAG + generate)."""
    if state.get("risk_hits"):
        return "policy_gate"
    if state.get("question_mode"):
        return "generate_question"
    return _disposition_entry()


def build_chat_graph(checkpointer=None):
    if checkpointer is None:
        from langgraph.checkpoint.memory import MemorySaver

        checkpointer = MemorySaver()

    graph = StateGraph(ChatState)
    graph.add_node("preprocess_input", preprocess_input_node)
    graph.add_node("ingest_input", ingest_input_node)
    graph.add_node("encode_input", encode_input_node)
    graph.add_node("enrich_checklist", enrich_checklist_node)
    graph.add_node("evaluate_coverage", evaluate_coverage_node)
    graph.add_node("plan_question", plan_question_node)
    graph.add_node("generate_question", generate_question_node)
    graph.add_node("retrieve_evidence", retrieve_evidence_node)
    graph.add_node("graph_traversal", graph_traversal_node)
    graph.add_node("generate_draft", generate_draft_node)
    graph.add_node("agentic_disposition", _agentic_disposition_node)
    graph.add_node("policy_gate", policy_gate_node)
    graph.add_node("finalize_response", finalize_response_node)

    graph.add_edge(START, "preprocess_input")
    graph.add_edge("preprocess_input", "ingest_input")
    graph.add_edge("ingest_input", "encode_input")
    graph.add_conditional_edges(
        "encode_input",
        _route_after_encode,
        {
            "policy_gate": "policy_gate",
            "enrich_checklist": "enrich_checklist",
        },
    )
    graph.add_edge("enrich_checklist", "evaluate_coverage")
    graph.add_edge("evaluate_coverage", "plan_question")
    graph.add_conditional_edges(
        "plan_question",
        _route_after_plan,
        {
            "policy_gate": "policy_gate",
            "generate_question": "generate_question",
            "retrieve_evidence": "retrieve_evidence",
            "agentic_disposition": "agentic_disposition",
        },
    )
    graph.add_edge("generate_question", "finalize_response")
    graph.add_edge("retrieve_evidence", "graph_traversal")
    graph.add_edge("graph_traversal", "generate_draft")
    graph.add_edge("generate_draft", "policy_gate")
    graph.add_edge("agentic_disposition", "policy_gate")
    graph.add_edge("policy_gate", "finalize_response")
    graph.add_edge("finalize_response", END)

    return graph.compile(checkpointer=checkpointer)
