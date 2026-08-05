from langchain_core.messages import AIMessage, HumanMessage

import logging

from app.orchestrator.checklist import ensure_checklist_ids, merge_checklist_items
from app.session_enrichment import append_turn_extraction, build_turn_extraction_record
from app.services.intake_enricher import propose_checklist_enrichment

from app.orchestrator.coverage import (

    coverage_intake_summary,

    evaluate_checklist_coverage,

)

from app.orchestrator.messages import conversation_history_before_last_user

from app.orchestrator.question_planner import plan_next_question

from app.orchestrator.slot_answers import credit_asked_slot_answer

from app.orchestrator.state import ChatState


from app.services.encoder import encode_user_message

from app.services.policy import apply_policy, hits_for_clinical_path

from app.services.preprocess import normalize_user_text

_log = logging.getLogger(__name__)

from app.services.rag import retrieve_evidence
from app.services.rag.chunk_retrieval import retrieve_rag_chunk_matches



# grab the most recent user message text

def _latest_user_text(messages: list) -> str:

    for m in reversed(messages):

        if isinstance(m, HumanMessage):

            c = m.content

            return c if isinstance(c, str) else str(c)

    return ""





# preprocess the input message with normalize_user_text

def preprocess_input_node(state: ChatState) -> ChatState:

    msgs = state.get("messages") or []

    text = _latest_user_text(msgs)

    state["message"] = text

    state["message_normalized"] = normalize_user_text(text)

    return state





# stub- future implementation may include logging, DB, abuse detection, validation

def ingest_input_node(state: ChatState) -> ChatState:

    return state





def encode_input_node(state: ChatState) -> ChatState:

    enc = encode_user_message(state["message_normalized"])

    prior = state.get("clinical_checklist") or []

    merged = merge_checklist_items(prior, enc.checklist.items)

    state["clinical_checklist"] = merged
    state["turn_start_checklist"] = [dict(x) for x in prior]
    state["encoder_turn_items"] = [item.model_dump() for item in enc.checklist.items]

    state["risk_hits"] = hits_for_clinical_path(

        enc.checklist, state["message_normalized"]

    )

    state["encoder_entities"] = [e.model_dump() for e in enc.entities]

    state["encoder_pooled_embedding"] = enc.pooled_embedding

    return state





def enrich_checklist_node(state: ChatState) -> ChatState:

    prior_turn = [dict(x) for x in (state.get("turn_start_checklist") or [])]
    encoder_merged = state.get("clinical_checklist") or []
    msgs = state.get("messages") or []
    history = conversation_history_before_last_user(msgs)
    extraction_history = state.get("extraction_history") or []
    turn_index = len(extraction_history) + 1
    latest_message = state.get("message_normalized", "")
    last_asked = state.get("last_asked_slot")

    # Deterministic credit for direct answers to the prior intake question
    # (e.g. user replies "Exercise" after a palliative ask). Runs before the
    # LLM enricher so a failed Vertex turn cannot leave the slot open.
    slot_credit = credit_asked_slot_answer(
        message=latest_message,
        last_asked_slot=last_asked,
        checklist=encoder_merged,
    )
    if slot_credit:
        encoder_merged = merge_checklist_items(encoder_merged, slot_credit)
        state["clinical_checklist"] = encoder_merged

    enrichment = propose_checklist_enrichment(
        checklist=encoder_merged,
        conversation_history=history,
        latest_user_message=latest_message,
        last_asked_slot=last_asked,
        comorbidities_acknowledged=bool(state.get("comorbidities_acknowledged")),
        session_id=state.get("session_id", ""),
        turn_index=turn_index,
    )

    final_checklist = ensure_checklist_ids([dict(x) for x in encoder_merged])
    if enrichment.resulting_checklist is not None:
        # Trusted post-filter snapshot (adds / modifies / deletes already validated).
        final_checklist = ensure_checklist_ids(
            [dict(x) for x in enrichment.resulting_checklist]
        )
        state["clinical_checklist"] = final_checklist
    elif enrichment.applied_items:
        # Backward-compatible path if only additions were returned.
        final_checklist = merge_checklist_items(encoder_merged, enrichment.applied_items)
        state["clinical_checklist"] = final_checklist
    else:
        state["clinical_checklist"] = final_checklist

    if enrichment.comorbidities_acknowledged:
        state["comorbidities_acknowledged"] = True

    # Stash the co-generated next question for the planner (one LLM call per turn).
    state["pending_intake_question"] = enrichment.next_question
    state["pending_intake_slot"] = enrichment.next_slot

    encoder_items = state.get("encoder_turn_items") or []
    state["extraction_history"] = append_turn_extraction(
        extraction_history,
        build_turn_extraction_record(
            turn_index=turn_index,
            user_message=state.get("message") or state.get("message_normalized") or "",
            turn_items=encoder_items,
            prior_checklist=prior_turn,
            merged_checklist=final_checklist,
            llm_enrichment=enrichment.to_log_dict(),
        ),
    )

    return state





# rebuild symptom instances and coverage report from merged checklist

def evaluate_coverage_node(state: ChatState) -> ChatState:

    coverage, assignments, ack = evaluate_checklist_coverage(

        checklist=state.get("clinical_checklist") or [],

        comorbidities_acknowledged=state.get("comorbidities_acknowledged", False),

        symptom_instances=state.get("symptom_instances"),

        active_symptom_id=(state.get("coverage") or {}).get("active_symptom_id"),

        last_asked_slot=state.get("last_asked_slot"),

        latest_user_message=state.get("message_normalized", ""),

        symptom_slot_assignments=state.get("symptom_slot_assignments"),

    )

    state["coverage"] = coverage

    state["symptom_instances"] = coverage.get("symptom_instances") or []

    state["symptom_slot_assignments"] = assignments

    state["comorbidities_acknowledged"] = ack

    return state





# set question_mode and one LLM-generated intake question (or disposition path)

def plan_question_node(state: ChatState) -> ChatState:

    coverage = state.get("coverage") or {}

    msgs = state.get("messages") or []

    history = conversation_history_before_last_user(msgs)

    q_mode, question, reason, slot, active_id = plan_next_question(

        coverage,

        risk_hits=state.get("risk_hits") or [],

        questions_asked=state.get("questions_asked", 0),

        comorbidities_acknowledged=state.get("comorbidities_acknowledged", False),

        checklist=state.get("clinical_checklist") or [],

        conversation_history=history,

        latest_user_message=state.get("message_normalized", ""),

        pending_question=state.get("pending_intake_question"),

        pending_slot=state.get("pending_intake_slot"),

    )

    # Consumed; clear so a later disposition path cannot reuse a stale draft.
    state["pending_intake_question"] = None
    state["pending_intake_slot"] = None

    state["question_mode"] = q_mode

    state["next_question"] = question

    state["question_reason"] = reason

    state["slot_being_asked"] = slot

    if active_id and coverage:

        coverage = dict(coverage)

        coverage["active_symptom_id"] = active_id

        state["coverage"] = coverage  # type: ignore[assignment]

    if state.get("risk_hits"):

        state["question_mode"] = False

        state["draft_response"] = ""

    return state





# append a single intake question as final_response (no RAG / disposition yet)

def generate_question_node(state: ChatState) -> ChatState:

    text = state.get("next_question") or (

        "Could you tell me a bit more about your symptoms?"

    )

    state["final_response"] = text

    state["draft_response"] = text

    state["questions_asked"] = state.get("questions_asked", 0) + 1

    if state.get("slot_being_asked"):

        state["last_asked_slot"] = state["slot_being_asked"]

    state["evidence"] = []

    state["escalated"] = False

    state["safety_reason"] = None

    # Clear in-memory LangGraph state for this question turn. Session JSON
    # merge preserves prior disposition_history / latest disposition snapshots.
    state["graph_traversal"] = None

    state["matched_factors"] = []

    state["candidate_conditions"] = []

    state["traversed_chunk_ids"] = []

    state["factor_matching_audit"] = None

    state["agent_trace"] = None

    return state





def retrieve_evidence_node(state: ChatState) -> ChatState:

    from app.config import settings
    from app.services.rag.chunk_retrieval import (
        chunk_matches_to_evidence,
        retrieve_rag_chunk_matches,
    )

    matches = []
    if settings.rag_load:
        matches = retrieve_rag_chunk_matches(
            state["message_normalized"],
            state.get("encoder_pooled_embedding") or None,
            state.get("clinical_checklist") or [],
        )

    state["chunk_matches"] = [m.model_dump() for m in matches]

    if settings.rag_load and not settings.graphrag_load:
        state["evidence"] = chunk_matches_to_evidence(matches)
    else:
        state["evidence"] = []

    return state





def graph_traversal_node(state: ChatState) -> ChatState:

    from app.config import settings

    from app.schemas import ChunkMatch
    from app.services.graphrag import traverse_from_turn
    from app.services.rag.evidence_builder import build_generator_evidence
    from app.services.rag.fusion import build_traversal_seeds

    if not settings.graphrag_load:
        return state

    raw_chunks = state.get("chunk_matches") or []
    chunk_matches = (
        [ChunkMatch.model_validate(c) for c in raw_chunks]
        if settings.rag_load
        else []
    )

    seeds = build_traversal_seeds(
        checklist=state.get("clinical_checklist") or [],
        chunk_matches=chunk_matches,
    )

    from app.services.rag.factor_matcher import build_factor_matching_audit

    factor_audit = build_factor_matching_audit(seeds.factor_matches)
    _log.info(
        "factor_matching_audit: matched=%s gaps=%s methods=%s",
        factor_audit["summary"]["matched_factors"],
        factor_audit["summary"]["gap_count"],
        factor_audit["summary"]["methods"],
    )

    trace = traverse_from_turn(

        checklist=state.get("clinical_checklist") or [],

        chunk_matches=chunk_matches,

        factor_matches=seeds.factor_matches,

        title=f"Chat turn: {state.get('session_id', '')}",

    )

    _log.info(
        "graph_traversal: factors=%s conditions=%s steps=%s",
        list(trace.matched_factors),
        list(trace.candidate_conditions)[:8],
        len(trace.steps),
    )

    state["matched_factors"] = trace.matched_factors

    state["candidate_conditions"] = trace.candidate_conditions

    state["traversed_chunk_ids"] = seeds.chunk_ids_in_trace(trace)

    graph_payload = trace.model_dump()
    graph_payload["factor_matching"] = factor_audit
    state["graph_traversal"] = graph_payload
    state["factor_matching_audit"] = factor_audit

    state["evidence"] = build_generator_evidence(
        trace=trace,
        chunk_matches=chunk_matches if settings.rag_load else None,
    )

    return state





# generate draft disposition using RAG evidence and intake summary

def generate_draft_node(state: ChatState) -> ChatState:

    from app.services.generator import generate_response, is_generator_system_failure

    msgs = state.get("messages") or []

    history = conversation_history_before_last_user(msgs)

    intake = coverage_intake_summary(state.get("coverage") or {})

    draft = generate_response(

        state["message_normalized"],

        state["evidence"],

        conversation_history=history,

        intake_summary=intake,

    )

    state["draft_response"] = draft

    state["generator_failed"] = is_generator_system_failure(draft)

    return state





# apply policy to draft response; RISK_CATALOG hits override with escalation copy

def policy_gate_node(state: ChatState) -> ChatState:

    escalated, reason, final_response = apply_policy(

        state.get("draft_response", ""),

        state.get("risk_hits") or [],

        generator_failed=bool(state.get("generator_failed")),

    )

    state["escalated"] = escalated

    state["safety_reason"] = reason

    state["final_response"] = final_response

    return state





# return final response as AI message for LangGraph output

def finalize_response_node(state: ChatState) -> dict:

    return {"messages": [AIMessage(content=state["final_response"])]}


