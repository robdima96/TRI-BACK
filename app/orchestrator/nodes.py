from langchain_core.messages import AIMessage, HumanMessage

from app.orchestrator.checklist import merge_checklist_items
from app.orchestrator.messages import conversation_history_before_last_user
from app.orchestrator.state import ChatState
from app.services.encoder import encode_user_message
from app.services.generator import generate_response
from app.services.policy import apply_policy, hits_for_clinical_path
from app.services.preprocess import normalize_user_text
from app.services.rag import retrieve_evidence

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

# stub- future implementation may include:
#   -logging
#   -saving raw messages to DB
#   -abuse detection 
#   -input validation
def ingest_input_node(state: ChatState) -> ChatState:
    return state


def encode_input_node(state: ChatState) -> ChatState:
    enc = encode_user_message(state["message_normalized"]) # encoding pipeline returns EncoderOutput
    prior = state.get("clinical_checklist") or [] # prior checklist items from previous turns
    state["clinical_checklist"] = merge_checklist_items(prior, enc.checklist.items) # merge new items with prior
    state["red_flag_hits"] = hits_for_clinical_path( # check for red flags via hits_for_clinical_path in policy.py
        enc.checklist, state["message_normalized"]
    )
    state["encoder_entities"] = [e.model_dump() for e in enc.entities]
    state["encoder_pooled_embedding"] = enc.pooled_embedding
    return state

# pass normalized message and embedding for hybrid RAG search
def retrieve_evidence_node(state: ChatState) -> ChatState:
    state["evidence"] = retrieve_evidence(
        state["message_normalized"],
        state.get("encoder_pooled_embedding", []) or [], # return empty list if no embedding available
    )
    return state

# generate draft response using LLM
def generate_draft_node(state: ChatState) -> ChatState:
    msgs = state.get("messages") or []
    history = conversation_history_before_last_user(msgs)
    state["draft_response"] = generate_response(
        state["message_normalized"],
        state["evidence"],
        conversation_history=history,
    )
    return state

# apply policy to draft response and return final response
def policy_gate_node(state: ChatState) -> ChatState:
    escalated, reason, final_response = apply_policy(
        state["draft_response"], state["red_flag_hits"]
    )
    state["escalated"] = escalated
    state["safety_reason"] = reason
    state["final_response"] = final_response
    return state

# return final response as AI message for LangGraph output
def finalize_response_node(state: ChatState) -> dict:
    return {"messages": [AIMessage(content=state["final_response"])]}
