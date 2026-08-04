"""DigiMSK session log browser — lightweight local debug UI.

Run from repo root or from Testing/:
  cd Testing
  pip install -r requirements.txt
  uvicorn app:app --reload --port 8765
Then open http://127.0.0.1:8765
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from session_index import (
    build_chat_turns,
    engagement_chart_payload,
    list_session_summaries,
    load_session_by_key,
    pretty_json,
    sessions_dir,
)

HERE = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(HERE / "templates"))

app = FastAPI(title="DigiMSK Session Lab", docs_url="/api/docs")
app.mount("/static", StaticFiles(directory=str(HERE / "static")), name="static")


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    sessions = list_session_summaries()
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "sessions": sessions,
            "sessions_dir": str(sessions_dir()),
            "session_count": len(sessions),
        },
    )


@app.get("/session/{file_key}", response_class=HTMLResponse)
def session_detail(request: Request, file_key: str) -> HTMLResponse:
    data = load_session_by_key(file_key)
    if data is None:
        raise HTTPException(status_code=404, detail=f"Session not found: {file_key}")
    turns = build_chat_turns(data)
    chart = engagement_chart_payload(data)
    return templates.TemplateResponse(
        request,
        "session.html",
        {
            "data": data,
            "turns": turns,
            "chart": chart,
            "chart_json": pretty_json(chart),
            "checklist": data.get("clinical_checklist") or [],
            "extraction_history": data.get("extraction_history") or [],
            "orchestrator": data.get("orchestrator"),
            "orchestrator_history": data.get("orchestrator_history") or [],
            "disposition_history": data.get("disposition_history") or [],
            "factor_audit": data.get("factor_matching_audit"),
            "agent_trace": data.get("agent_trace"),
            "graph_traversal": data.get("graph_traversal"),
            "matched_factors": data.get("matched_factors") or [],
            "candidate_conditions": data.get("candidate_conditions") or [],
            "traversed_chunk_ids": data.get("traversed_chunk_ids") or [],
            "raw_json": pretty_json(
                {k: v for k, v in data.items() if not str(k).startswith("_")}
            ),
        },
    )


@app.get("/api/sessions")
def api_sessions() -> list[dict]:
    return list_session_summaries()


@app.get("/api/session/{file_key}")
def api_session(file_key: str) -> dict:
    data = load_session_by_key(file_key)
    if data is None:
        raise HTTPException(status_code=404, detail=f"Session not found: {file_key}")
    return data
