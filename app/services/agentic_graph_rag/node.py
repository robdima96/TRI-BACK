"""LangGraph node for the toggleable agentic disposition path.

Replaces the deterministic ``retrieve_evidence -> graph_traversal ->
generate_draft`` sub-chain with a single node when
``settings.disposition_mode == "agentic"``. It still:

- runs the deterministic ground-truth traversal first (anchor + UI/Arm-3 parity),
- writes the same state fields the deterministic path does
  (``evidence``, ``draft_response``, ``graph_traversal``, ``matched_factors``,
  ``candidate_conditions``, ``traversed_chunk_ids``), and
- embeds the full agent audit trail in ``graph_traversal["agent_trace"]`` and
  ``state["agent_trace"]``.

Any failure (generator unavailable, agent parse/backends error) degrades cleanly
to the deterministic draft, so enabling the toggle can never leave a turn without
a grounded response. ``policy_gate`` still runs afterwards as the outer safety net.
"""

from __future__ import annotations

import logging

from app.orchestrator.state import ChatState

_log = logging.getLogger(__name__)


def agentic_disposition_node(state: ChatState) -> ChatState:
    from app.config import settings
    from app.schemas import ChunkMatch
    from app.services.agentic_graph_rag.agent import run_disposition_agent
    from app.services.agentic_graph_rag.ontology import load_ontology
    from app.services.graphrag import traverse_from_turn
    from app.services.generator import generate_response, generator_model_configured
    from app.orchestrator.coverage import coverage_intake_summary
    from app.orchestrator.messages import conversation_history_before_last_user
    from app.services.rag.chunk_retrieval import retrieve_rag_chunk_matches
    from app.services.rag.evidence_builder import build_generator_evidence
    from app.services.rag.fusion import build_traversal_seeds

    query = state["message_normalized"]
    checklist = state.get("clinical_checklist") or []

    # 1. Deterministic ground-truth retrieval + traversal (anchor for the agent).
    chunk_matches: list[ChunkMatch] = []
    if settings.rag_load:
        raw = retrieve_rag_chunk_matches(
            query,
            state.get("encoder_pooled_embedding") or None,
            checklist,
        )
        chunk_matches = list(raw)
    state["chunk_matches"] = [m.model_dump() for m in chunk_matches]

    trace = traverse_from_turn(
        checklist=checklist,
        chunk_matches=chunk_matches,
        factor_matches=build_traversal_seeds(
            checklist=checklist, chunk_matches=chunk_matches
        ).factor_matches,
        title=f"Chat turn (agentic): {state.get('session_id', '')}",
    )
    seeds = build_traversal_seeds(checklist=checklist, chunk_matches=chunk_matches)
    baseline_evidence = build_generator_evidence(
        trace=trace,
        chunk_matches=chunk_matches if settings.rag_load else None,
    )

    state["matched_factors"] = trace.matched_factors
    state["candidate_conditions"] = trace.candidate_conditions
    state["traversed_chunk_ids"] = seeds.chunk_ids_in_trace(trace)
    state["evidence"] = baseline_evidence

    graph_payload = trace.model_dump()

    # 2. Run the agent (falls back to deterministic draft on any problem).
    intake = coverage_intake_summary(state.get("coverage") or {})
    history = conversation_history_before_last_user(state.get("messages") or [])

    if not generator_model_configured():
        _log.warning("agentic disposition: generator unavailable; deterministic draft")
        state["draft_response"] = generate_response(
            query, baseline_evidence, conversation_history=history, intake_summary=intake
        )
        graph_payload["agent_trace"] = {"status": "fallback", "stop_reason": "generator_unavailable"}
        state["agent_trace"] = graph_payload["agent_trace"]
        state["graph_traversal"] = graph_payload
        return state

    ontology = load_ontology()
    final_text, agent_trace = run_disposition_agent(
        query=query,
        checklist=checklist,
        chunk_matches=chunk_matches,
        ontology=ontology,
        matched_factors=list(trace.matched_factors),
        deterministic_conditions=list(trace.candidate_conditions),
        baseline_evidence=baseline_evidence,
        intake_summary=intake,
        conversation_history=history,
        max_steps=max(1, int(settings.agentic_max_steps)),
    )

    if final_text is None:
        _log.info("agentic disposition fell back (%s)", agent_trace.stop_reason)
        state["draft_response"] = generate_response(
            query, baseline_evidence, conversation_history=history, intake_summary=intake
        )
    else:
        state["draft_response"] = final_text

    compact = agent_trace.compact()
    graph_payload["agent_trace"] = compact
    state["agent_trace"] = compact
    state["graph_traversal"] = graph_payload
    return state
