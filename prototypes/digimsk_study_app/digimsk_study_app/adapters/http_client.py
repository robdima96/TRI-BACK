"""HTTP client for bot/ FastAPI chat endpoint."""

from __future__ import annotations

import time
from typing import Any

import httpx

from digimsk_study_app.adapters.base import ChatTurnResult
from digimsk_study_app.config import BOT_API_KEY, CHATBOT_BASE_URL


async def call_chat_api(session_id: str, message: str) -> ChatTurnResult:
    url = f"{CHATBOT_BASE_URL}/api/v1/chat"
    headers: dict[str, str] = {}
    if BOT_API_KEY:
        headers["Authorization"] = f"Bearer {BOT_API_KEY}"
    started = time.perf_counter()
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(
            url,
            json={"session_id": session_id, "message": message},
            headers=headers,
        )
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()
    elapsed_ms = (time.perf_counter() - started) * 1000.0

    citations = [
        {
            "source": c.get("source", ""),
            "snippet": c.get("snippet", ""),
            "score": float(c.get("score") or 0.0),
            "chunk_id": c.get("chunk_id") or "",
        }
        for c in data.get("citations") or []
    ]

    return ChatTurnResult(
        session_id=data.get("session_id", session_id),
        response=data.get("response", ""),
        citations=citations,
        escalated=bool(data.get("escalated")),
        safety_reason=data.get("safety_reason"),
        question_mode=bool(data.get("question_mode")),
        questions_asked=int(data.get("questions_asked") or 0),
        coverage_ready=bool(data.get("coverage_ready")),
        graph_traversal=data.get("graph_traversal"),
        matched_factors=list(data.get("matched_factors") or []),
        candidate_conditions=list(data.get("candidate_conditions") or []),
        traversed_chunk_ids=list(data.get("traversed_chunk_ids") or []),
        clinical_checklist=list(data.get("clinical_checklist") or []),
        extraction_history=list(data.get("extraction_history") or []),
        turn_extraction=data.get("turn_extraction"),
        round_trip_ms=elapsed_ms,
    )
