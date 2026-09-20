"""HTTP client for bot/ FastAPI chat endpoint."""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from tri_back_study_app.adapters.base import ChatTurnResult
from tri_back_study_app.config import BOT_API_KEY, CHATBOT_BASE_URL

_log = logging.getLogger(__name__)

_METADATA_IDENTITY = (
    "http://metadata.google.internal/computeMetadata/v1/"
    "instance/service-accounts/default/identity"
)


def fetch_cloud_run_identity_token(audience: str, *, timeout: float = 2.0) -> str | None:
    """ID token for private Cloud Run. None on localhost or if metadata is absent."""
    audience = (audience or "").strip().rstrip("/")
    if not audience.startswith("https://"):
        return None
    try:
        resp = httpx.get(
            _METADATA_IDENTITY,
            params={"audience": audience},
            headers={"Metadata-Flavor": "Google"},
            timeout=timeout,
        )
        if resp.status_code == 200:
            token = (resp.text or "").strip()
            return token or None
    except Exception as exc:  # noqa: BLE001 — local/dev has no metadata server
        _log.debug("Cloud Run identity token unavailable: %s", exc)
    return None


def bot_headers(*, api_key: str | None = None, base_url: str | None = None) -> dict[str, str]:
    """App Bearer key plus Cloud Run ``X-Serverless-Authorization`` when hosted.

    Private Cloud Run treats ``Authorization`` as a Google ID token. Sending only
    ``TRI_BACK_BOT_API_KEY`` yields 401 before FastAPI sees the request.
    """
    key = (BOT_API_KEY if api_key is None else api_key) or ""
    key = key.strip()
    url = (CHATBOT_BASE_URL if base_url is None else base_url) or ""
    headers: dict[str, str] = {}
    id_token = fetch_cloud_run_identity_token(url)
    if key:
        headers["Authorization"] = f"Bearer {key}"
        if id_token:
            headers["X-Serverless-Authorization"] = f"Bearer {id_token}"
    elif id_token:
        headers["Authorization"] = f"Bearer {id_token}"
    return headers


def _bot_headers() -> dict[str, str]:
    return bot_headers()


async def ping_bot_ready(*, timeout: float = 120.0) -> bool:
    """Wake the bot Cloud Run instance / confirm readiness (best-effort).

    Hits ``GET /ready`` so a cold start pays GliNER/Vertex lifespan warmup
    before the user's first real chat turn. Failures are logged, not raised.
    """
    url = f"{CHATBOT_BASE_URL}/ready"
    started = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url, headers=_bot_headers())
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        ok = resp.status_code == 200
        _log.info(
            "bot ready ping status=%s elapsed_ms=%.0f body=%s",
            resp.status_code,
            elapsed_ms,
            (resp.text or "")[:200],
        )
        return ok
    except Exception as exc:  # noqa: BLE001 — warmup must not block login/chat
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        _log.warning("bot ready ping failed after %.0fms: %s", elapsed_ms, exc)
        return False


async def call_chat_api(session_id: str, message: str) -> ChatTurnResult:
    url = f"{CHATBOT_BASE_URL}/api/v1/chat"
    headers = _bot_headers()
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
        intake_traversal=data.get("intake_traversal"),
        matched_factors=list(data.get("matched_factors") or []),
        candidate_conditions=list(data.get("candidate_conditions") or []),
        traversed_chunk_ids=list(data.get("traversed_chunk_ids") or []),
        clinical_checklist=list(data.get("clinical_checklist") or []),
        extraction_history=list(data.get("extraction_history") or []),
        turn_extraction=data.get("turn_extraction"),
        round_trip_ms=elapsed_ms,
    )


async def call_rephrase_api(session_id: str, message_id: str) -> ChatTurnResult:
    url = f"{CHATBOT_BASE_URL}/api/v1/rephrase"
    headers = _bot_headers()
    started = time.perf_counter()
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(
            url,
            json={"session_id": session_id, "message_id": message_id},
            headers=headers,
        )
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    return ChatTurnResult(
        session_id=data.get("session_id", session_id),
        response=data.get("response", ""),
        question_mode=bool(data.get("question_mode", True)),
        questions_asked=int(data.get("questions_asked") or 0),
        round_trip_ms=elapsed_ms,
    )
