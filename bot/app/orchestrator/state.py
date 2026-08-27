from typing import Annotated, NotRequired, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages

from app.orchestrator.intake_models import CoverageReport, SlotName, SymptomInstance
from app.schemas import Evidence

# Checklist key tuple persisted in symptom_slot_assignments (text, kind, source, label).
ChecklistKeyTuple = tuple[str, str, str, str]


# single shared state object that every node in the graph reads from and writes to
class ChatState(TypedDict):
    session_id: str
    # First-class chat transcript; add_messages merges incremental updates per turn.
    messages: Annotated[list[AnyMessage], add_messages]
    # Latest raw user text (set in preprocess from trailing HumanMessage).
    message: str
    message_normalized: str
    # Orchestrator checklist history (encoder + pattern/NER extraction)
    clinical_checklist: list[dict[str, str]]
    # Per-turn pattern / GliNER / safety / LLM extraction snapshots
    extraction_history: NotRequired[list[dict]]
    # Transient per-turn fields (set in encode_input, consumed in enrich_checklist)
    turn_start_checklist: NotRequired[list[dict[str, str]]]
    encoder_turn_items: NotRequired[list[dict[str, str]]]
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
    # Draft question from the combined enrich+question LLM call (consumed by planner).
    pending_intake_question: NotRequired[str | None]
    pending_intake_slot: NotRequired[SlotName | None]

    # --- graph traversal (local v1 CSV) ---
    chunk_matches: NotRequired[list[dict[str, str | float]]]
    graph_traversal: NotRequired[dict | None]
    matched_factors: NotRequired[list[str]]
    candidate_conditions: NotRequired[list[str]]
    traversed_chunk_ids: NotRequired[list[str]]
    # Per-item factor matcher decisions + coverage gaps (also nested under graph_traversal).
    factor_matching_audit: NotRequired[dict | None]
    # Audit trail for the agentic disposition path (DIGIMSK_DISPOSITION_MODE=agentic)
    agent_trace: NotRequired[dict | None]
    # Authoritative graph rank + factor provenance for disposition generation.
    disposition_brief: NotRequired[dict | None]
