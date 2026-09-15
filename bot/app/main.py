from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from langchain_core.messages import HumanMessage

from app.config import settings
from app.config import validate_retrieval_paths
from app.readiness import readiness_payload
from app.orchestrator.checkpointing import close_checkpointer, get_checkpointer
from app.orchestrator.graph import build_chat_graph
from app.orchestrator.messages import transcript_from_messages
from app.schemas import ChatRequest, ChatResponse
from app.session_enrichment import (
    build_disposition_record,
    build_intake_record,
    build_orchestrator_snapshot,
    exposed_chat_graph_fields,
)
from app.session_store import save_session
from app.orchestrator.session_resume import maybe_resume_from_session
from app.services.public_host.api_auth import (
    enforce_chat_rate_limit,
    require_bot_api_key,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    validate_retrieval_paths()
    # Pay GliNER / optional embedding / Vertex handshake cost at process start
    # so the first real chat turn is not a 20–40s cold start.
    from app.services.warmup import warmup_runtime

    warmup_runtime()
    yield
    close_checkpointer()

# Create FastAPI instance
# build the chat graph and get the SQLite checkpointer
app = FastAPI(
    title=settings.app_name, version=settings.app_version, lifespan=lifespan)
chat_graph = build_chat_graph(checkpointer=get_checkpointer())


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": settings.app_name, "environment": settings.environment}


@app.get("/ready")
def ready() -> JSONResponse:
    """Readiness: RAG (if enabled), checkpointer, generator weights, encoder config path."""
    body = readiness_payload()
    code = 200 if body["status"] == "ready" else 503
    return JSONResponse(content=body, status_code=code)

# chat endpoint
# every time a user sends a message, this endpoint is called
@app.post(
    "/api/v1/chat",
    response_model=ChatResponse,
    dependencies=[Depends(require_bot_api_key)],
)
def chat(req: ChatRequest, request: Request) -> ChatResponse:
    if not req.session_id.strip():
        raise HTTPException(status_code=400, detail="session_id is required")

    sid = req.session_id.strip()
    enforce_chat_rate_limit(request, sid)
    config = {"configurable": {"thread_id": sid}} # LangGraph thread_id maps to chat session_id
    maybe_resume_from_session(chat_graph, config, sid)

    state = chat_graph.invoke( # invoke the chat graph with the session_id and the user message
                               # all other vars restored from SQLite checkpoint using thread_id
        {
            "session_id": req.session_id,
            "messages": [HumanMessage(content=req.message)],
        },
        config,
    )

    # JSON snapshot for logging / auditing (in addition to LangGraph checkpoints).
    extraction_history = list(state.get("extraction_history") or [])
    turn_extraction = extraction_history[-1] if extraction_history else None
    turn_index = int(
        (turn_extraction or {}).get("turn_index")
        or len(extraction_history)
        or 1
    )
    transcript = transcript_from_messages(state["messages"])
    graph_trace, intake_trace = exposed_chat_graph_fields(state)
    factor_audit = state.get("factor_matching_audit")
    orchestrator = build_orchestrator_snapshot(state, turn_index=turn_index)
    disposition = build_disposition_record(state, turn_index=turn_index)
    intake = build_intake_record(state, turn_index=turn_index)

    # Disposition fields are only passed when this turn produced a disposition
    # record; merge_session_fields preserves prior disposition_* on question turns.
    save_kwargs: dict = {
        "clinical_checklist": state["clinical_checklist"],
        "messages": transcript,
        "extraction_history": extraction_history,
        "orchestrator": orchestrator,
        "factor_states": dict(state.get("factor_states") or {}),
        "session_phase": state.get("session_phase") or "intake",
    }
    if disposition is not None:
        save_kwargs["disposition"] = disposition
    if intake is not None:
        save_kwargs["intake"] = intake
    save_session(sid, **save_kwargs)

    coverage = state.get("coverage") or {}
    return ChatResponse(
        session_id=state["session_id"],
        response=state["final_response"],
        citations=state.get("evidence") or [],
        escalated=state["escalated"],
        safety_reason=state["safety_reason"],
        question_mode=bool(state.get("question_mode")),
        questions_asked=int(state.get("questions_asked", 0)),
        coverage_ready=bool(coverage.get("ready_for_disposition")),
        graph_traversal=graph_trace,
        intake_traversal=intake_trace,
        matched_factors=list(state.get("matched_factors") or []),
        candidate_conditions=list(state.get("candidate_conditions") or []),
        traversed_chunk_ids=list(state.get("traversed_chunk_ids") or []),
        factor_matching_audit=factor_audit,
        clinical_checklist=list(state.get("clinical_checklist") or []),
        extraction_history=extraction_history,
        turn_extraction=turn_extraction,
    )
