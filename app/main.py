from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from langchain_core.messages import HumanMessage

from app.config import settings
from app.readiness import readiness_payload
from app.orchestrator.checkpointing import close_checkpointer, get_checkpointer
from app.orchestrator.graph import build_chat_graph
from app.orchestrator.messages import transcript_from_messages
from app.schemas import ChatRequest, ChatResponse
from app.session_store import save_session


@asynccontextmanager
async def lifespan(app: FastAPI):
    # nothing happens on startup
    yield
    # this runs on shutdown
    close_checkpointer() # close the checkpoint database

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
    save_session(
        sid,
        clinical_checklist=state["clinical_checklist"],
        messages=transcript_from_messages(state["messages"]),
    )

    return ChatResponse(
        session_id=state["session_id"],
        response=state["final_response"], 
        citations=state["evidence"], # from RAG search
        escalated=state["escalated"], # from policy
        safety_reason=state["safety_reason"], # from policy
    )
