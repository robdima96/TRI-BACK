"""Independent agentic disposition node.

The node shares intake factor matching and optional Chroma retrieval with the
deterministic path, but it never runs deterministic graph traversal/ranking
before the agent. Graph paths are inspected lazily through tools. A
deterministic traversal/draft is invoked only as an explicitly logged fallback.
"""

from __future__ import annotations

import logging

from app.orchestrator.state import ChatState

_log = logging.getLogger(__name__)


def agentic_disposition_node(state: ChatState) -> ChatState:
    from app.config import settings
    from app.schemas import ChunkMatch
    from app.services.agentic_graph_rag.agent import run_disposition_agent
    from app.services.agentic_graph_rag.ontology import (
        load_ontology,
        tally_touched_conditions,
    )
    from app.services.generator import generator_model_configured
    from app.orchestrator.coverage import coverage_intake_summary
    from app.orchestrator.messages import conversation_history_before_last_user
    from app.services.rag.chunk_retrieval import retrieve_rag_chunk_matches
    from app.services.rag.evidence_builder import (
        build_generator_evidence,
        evidence_from_chunk_ids,
    )
    from app.services.rag.fusion import build_traversal_seeds

    query = state["message_normalized"]
    checklist = state.get("clinical_checklist") or []

    # Shared observation prep: optional Chroma retrieval + checklist factor match.
    # This does not traverse paths or score/rank conditions.
    chunk_matches: list[ChunkMatch] = []
    if settings.rag_load:
        raw = retrieve_rag_chunk_matches(
            query,
            state.get("encoder_pooled_embedding") or None,
            checklist,
        )
        chunk_matches = list(raw)
    state["chunk_matches"] = [m.model_dump() for m in chunk_matches]

    seeds = build_traversal_seeds(checklist=checklist, chunk_matches=chunk_matches)
    from app.services.rag.factor_matcher import build_factor_matching_audit

    factor_audit = build_factor_matching_audit(seeds.factor_matches)
    matched_factors = seeds.matched_factor_names
    ontology = load_ontology()
    touched_conditions = tally_touched_conditions(matched_factors, ontology)
    baseline_evidence = build_generator_evidence(
        trace=None,
        chunk_matches=chunk_matches if settings.rag_load else None,
    )

    state["matched_factors"] = matched_factors
    state["candidate_conditions"] = []
    state["traversed_chunk_ids"] = list(seeds.chunk_ids)
    state["evidence"] = baseline_evidence
    state["factor_matching_audit"] = factor_audit
    intake = coverage_intake_summary(state.get("coverage") or {})
    history = conversation_history_before_last_user(state.get("messages") or [])

    if not generator_model_configured():
        return _deterministic_fallback(
            state=state,
            query=query,
            checklist=checklist,
            chunk_matches=chunk_matches,
            factor_matches=list(seeds.factor_matches),
            factor_audit=factor_audit,
            history=history,
            intake=intake,
            stop_reason="generator_unavailable",
        )

    final_text, agent_trace = run_disposition_agent(
        query=query,
        checklist=checklist,
        chunk_matches=chunk_matches,
        ontology=ontology,
        matched_factors=matched_factors,
        touched_conditions=touched_conditions,
        baseline_evidence=baseline_evidence,
        intake_summary=intake,
        conversation_history=history,
        max_steps=max(1, int(settings.agentic_max_steps)),
        precomputed_factor_matches=list(seeds.factor_matches),
        graph_enabled=settings.graphrag_load,
    )

    if final_text is None:
        return _deterministic_fallback(
            state=state,
            query=query,
            checklist=checklist,
            chunk_matches=chunk_matches,
            factor_matches=list(seeds.factor_matches),
            factor_audit=factor_audit,
            history=history,
            intake=intake,
            stop_reason=agent_trace.stop_reason or "agent_no_final",
            agent_trace=agent_trace.compact(),
        )

    state["draft_response"] = final_text
    state["generator_failed"] = False

    used_ids = list(agent_trace.used_chunk_ids)
    if used_ids:
        state["evidence"] = evidence_from_chunk_ids(
            used_ids,
            chunk_matches=chunk_matches,
            baseline=baseline_evidence,
        )
        merged_ids = list(state.get("traversed_chunk_ids") or [])
        for cid in used_ids:
            if cid not in merged_ids:
                merged_ids.append(cid)
        state["traversed_chunk_ids"] = merged_ids

    state["candidate_conditions"] = list(agent_trace.used_conditions)

    # Always emit a schema-valid trace envelope. Study Arm-2/Arm-3 clients
    # validate this payload and silently drop malformed dicts, so a turn where
    # the agent touched no graph conditions must still carry matched factors.
    graph_payload = _empty_trace_payload(
        session_id=str(state.get("session_id", "")),
        matched_factors=matched_factors,
    )
    if settings.graphrag_load and agent_trace.used_conditions:
        from app.services.graphrag.condition_traversals import (
            build_agent_provenance_trace,
        )

        provenance = build_agent_provenance_trace(
            checklist=checklist,
            used_factors=list(agent_trace.used_factors),
            used_conditions=list(agent_trace.used_conditions),
            factors_by_condition=dict(ontology.factors_by_condition),
            title=f"Chat turn (agentic provenance): {state.get('session_id', '')}",
        )
        graph_payload = provenance.model_dump()
        graph_payload["inference"] = "agentic_provenance_unscored"

    compact = agent_trace.compact()
    compact["fallback_used"] = False
    graph_payload["agent_trace"] = compact
    graph_payload["factor_matching"] = factor_audit
    state["agent_trace"] = compact
    state["graph_traversal"] = graph_payload
    return state


def _empty_trace_payload(
    *,
    session_id: str,
    matched_factors: list[str],
) -> dict:
    """Minimal, schema-valid traversal payload with no conditions asserted."""
    import uuid

    from app.services.graphrag.schemas import GraphTraversalTrace

    trace = GraphTraversalTrace(
        trace_id=f"agentic-{uuid.uuid4().hex[:12]}",
        title=f"Chat turn (agentic, no graph conditions): {session_id}",
        matched_factors=list(matched_factors),
    )
    payload = trace.model_dump()
    payload["inference"] = "agentic_no_graph_conditions"
    return payload


def _deterministic_fallback(
    *,
    state: ChatState,
    query: str,
    checklist: list[dict[str, str]],
    chunk_matches: list,
    factor_matches: list,
    factor_audit: dict,
    history: list[dict[str, str]],
    intake: str,
    stop_reason: str,
    agent_trace: dict | None = None,
) -> ChatState:
    """Run deterministic disposition only after the independent agent fails."""
    from app.config import settings
    from app.services.generator import generate_response, is_generator_system_failure
    from app.services.rag.evidence_builder import build_generator_evidence

    trace = None
    if settings.graphrag_load:
        from app.services.graphrag import traverse_from_turn

        trace = traverse_from_turn(
            checklist=checklist,
            chunk_matches=chunk_matches if settings.rag_load else [],
            factor_matches=factor_matches,
            title=f"Chat turn (agentic fallback): {state.get('session_id', '')}",
        )
    evidence = build_generator_evidence(
        trace=trace,
        chunk_matches=chunk_matches if settings.rag_load else None,
    )
    draft = generate_response(
        query,
        evidence,
        conversation_history=history,
        intake_summary=intake,
    )
    fallback_log = dict(agent_trace or {})
    fallback_log.update(
        {
            "status": "fallback",
            "stop_reason": stop_reason,
            "fallback_used": True,
            "fallback_mode": "deterministic",
        }
    )
    state["draft_response"] = draft
    state["generator_failed"] = is_generator_system_failure(draft)
    state["evidence"] = evidence
    state["agent_trace"] = fallback_log
    if trace is not None:
        state["matched_factors"] = list(trace.matched_factors)
        state["candidate_conditions"] = list(trace.candidate_conditions)
        state["traversed_chunk_ids"] = list(
            dict.fromkeys(step.chunk_id for step in trace.steps if step.chunk_id)
        )
        payload = trace.model_dump()
    else:
        payload = _empty_trace_payload(
            session_id=str(state.get("session_id", "")),
            matched_factors=list(state.get("matched_factors") or []),
        )
    payload["factor_matching"] = factor_audit
    payload["agent_trace"] = fallback_log
    payload["inference"] = "deterministic_fallback"
    state["graph_traversal"] = payload
    _log.warning("agentic disposition used deterministic fallback: %s", stop_reason)
    return state
