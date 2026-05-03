from typing import Annotated, NotRequired, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages

from app.schemas import Evidence

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
    # Named policy ids from :data:`app.services.policy.RISK_CATALOG`
    red_flag_hits: list[str]
    encoder_entities: list[dict[str, str]]
    encoder_pooled_embedding: list[float]
    evidence: list[Evidence]
    draft_response: str
    final_response: str
    escalated: bool
    safety_reason: str | None
