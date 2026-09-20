from typing import Annotated, NotRequired, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages

from app.orchestrator.intake_models import CoverageReport, SlotName, SymptomInstance
from app.schemas import ChecklistItemDump, Evidence

# Checklist key tuple persisted in symptom_slot_assignments (text, kind, source, label).
ChecklistKeyTuple = tuple[str, str, str, str]


# single shared state object that every node in the graph reads from and writes to
class ChatState(TypedDict):
    session_id: str
    # Stamped on first ingest; later turns keep this even if the request differs.
    triage_profile_id: NotRequired[str]
    # Incoming request id (not persisted as the session contract).
    requested_triage_profile_id: NotRequired[str]
    # First-class chat transcript; add_messages merges incremental updates per turn.
    messages: Annotated[list[AnyMessage], add_messages]
    # Latest raw user text (set in preprocess from trailing HumanMessage).
    message: str
    message_normalized: str
    # Orchestrator checklist history (encoder + pattern/NER extraction)
    clinical_checklist: list[ChecklistItemDump]
    # Per-turn pattern / GliNER / safety / LLM extraction snapshots
    extraction_history: NotRequired[list[dict]]
    # Transient per-turn fields (set in encode_input, consumed in enrich_checklist)
    turn_start_checklist: NotRequired[list[ChecklistItemDump]]
    encoder_turn_items: NotRequired[list[ChecklistItemDump]]
    # Named policy ids from :data:`app.services.policy.RISK_CATALOG`
    risk_hits: list[str]
    encoder_entities: list[dict[str, str]]
    encoder_pooled_embedding: list[float]
    evidence: list[Evidence]
    draft_response: str
    final_response: str
    escalated: bool
    safety_reason: str | None
    # Set when draft_response is the non-clinical generator system-failure copy.
    generator_failed: NotRequired[bool]
    generator_failure_kind: NotRequired[str | None]
    # True only on the canned post-disposition reply this turn (not the
    # disposition turn that first set session_phase=dormant).
    canned_dormant: NotRequired[bool]

    # --- conversational intake (coverage + question loop) ---
    symptom_instances: NotRequired[list[SymptomInstance]]
    comorbidities_acknowledged: NotRequired[bool]
    coverage: NotRequired[CoverageReport]
    symptom_slot_assignments: NotRequired[dict[str, dict[str, list[ChecklistKeyTuple]]]]
    question_mode: NotRequired[bool]
    next_question: NotRequired[str | None]
    question_reason: NotRequired[str | None]
    questions_asked: NotRequired[int]
    last_asked_slot: NotRequired[SlotName | None]
    slot_being_asked: NotRequired[SlotName | None]
    # intake until a disposition/escalation is issued; then dormant until symptoms change.
    session_phase: NotRequired[str]
    symptoms_changed: NotRequired[bool]
    # Canonical Factor name last asked (parallel to last_asked_slot). None on slot turns.
    asked_factor: NotRequired[str | None]
    # Coherence guard: previous ranker topic + tier (survives question turns).
    last_rank_topic: NotRequired[str | None]
    last_rank_tier: NotRequired[int | None]
    # Test/debug hook: force the next question to be this Factor (consumed once).
    force_factor_ask: NotRequired[str | None]
    # Draft question from the combined enrich+question LLM call (consumed by planner).
    pending_intake_question: NotRequired[str | None]
    pending_intake_slot: NotRequired[SlotName | None]

    # --- graph traversal (local v1 CSV) ---
    chunk_matches: NotRequired[list[dict[str, str | float]]]
    graph_traversal: NotRequired[dict | None]
    # Arm-3 View B: planner slice on question turns; finalize overwrites with
    # the accumulated interview path at disposition. Separate from
    # graph_traversal so neither field clobbers the other.
    intake_traversal: NotRequired[dict | None]
    matched_factors: NotRequired[list[str]]
    # Canonical Factor name -> unknown|affirmed|denied. Absent key == unknown.
    # Separate from ChecklistItem so denied/affirmed rows do not collide on
    # content_dedupe_key. Denied factors must not appear in matched_factors.
    factor_states: NotRequired[dict[str, str]]
    # Post-encode speech-act split (polarity / statement / question spans).
    utterance_analysis: NotRequired[dict]
    # Graph-grounded prefix prepended to the planner's next question.
    patient_question_brief: NotRequired[str | None]
    # Per-turn intake enricher judgment of the last asked floor slot.
    slot_reply: NotRequired[str | None]
    # LLM acknowledgement after a usable slot answer (null when answering a Q).
    intake_ack: NotRequired[str | None]
    candidate_conditions: NotRequired[list[str]]
    traversed_chunk_ids: NotRequired[list[str]]
    # Per-item factor matcher decisions + coverage gaps (also nested under graph_traversal).
    factor_matching_audit: NotRequired[dict | None]
    # Audit trail for the agentic disposition path (TRI_BACK_DISPOSITION_MODE=agentic)
    agent_trace: NotRequired[dict | None]
    # Authoritative graph rank + factor provenance for disposition generation.
    disposition_brief: NotRequired[dict | None]
