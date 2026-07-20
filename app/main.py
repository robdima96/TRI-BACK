from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from langchain_core.messages import HumanMessage

from app.config import settings
from app.config import validate_retrieval_paths
from app.readiness import readiness_payload
from app.orchestrator.checkpointing import close_checkpointer, get_checkpointer
from app.orchestrator.graph import build_chat_graph
from app.orchestrator.messages import transcript_from_messages
from app.schemas import ChatRequest, ChatResponse
from app.session_store import save_session


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
@app.post("/api/v1/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    if not req.session_id.strip():
        raise HTTPException(status_code=400, detail="session_id is required")

    sid = req.session_id.strip()
    config = {"configurable": {"thread_id": sid}} # LangGraph thread_id maps to chat session_id

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
    transcript = transcript_from_messages(state["messages"])
    save_session(
        sid,
        clinical_checklist=state["clinical_checklist"],
        messages=transcript,
        extraction_history=extraction_history,
    )

    coverage = state.get("coverage") or {}
    graph_trace = state.get("graph_traversal")
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
        matched_factors=list(state.get("matched_factors") or []),
        candidate_conditions=list(state.get("candidate_conditions") or []),
        traversed_chunk_ids=list(state.get("traversed_chunk_ids") or []),
        clinical_checklist=list(state.get("clinical_checklist") or []),
        extraction_history=extraction_history,
        turn_extraction=turn_extraction,
    )
