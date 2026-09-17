"""Remote and local text generation backends for ``generator.py``."""

from __future__ import annotations

import logging
import time
from typing import Any

from app.config import settings

_log = logging.getLogger(__name__)

_MISSING_GENAI = "google-genai not installed; pip install -e '.[generator-api]'"

# ``vertexai=True`` is the Vertex AI / Agent Platform client flag. Google's
# current README also lists ``enterprise=True`` after the Agent Platform
# rename; we keep ``vertexai=True`` and pass project+location explicitly so
# ambient GOOGLE_CLOUD_* / GOOGLE_GENAI_USE_ENTERPRISE cannot override
# TRI_BACK_VERTEX_*.
_vertex_client: Any = None

DEFAULT_THINKING_LEVEL = "MINIMAL"
_ALLOWED_THINKING = frozenset({"MINIMAL", "LOW", "MEDIUM", "HIGH"})
_RETRY_ATTEMPTS = 2
_RETRY_SLEEP_SEC = 0.5


def _genai_types() -> Any:
    try:
        from google.genai import types
    except ImportError as exc:
        raise RuntimeError(_MISSING_GENAI) from exc
    return types


def _split_system_messages(
    messages: list[dict[str, str]],
) -> tuple[str | None, list[dict[str, str]]]:
    """Peel ``role=system`` turns into a Vertex system_instruction string."""
    parts: list[str] = []
    rest: list[dict[str, str]] = []
    for turn in messages:
        if turn.get("role") == "system":
            content = (turn.get("content") or "").strip()
            if content:
                parts.append(content)
        else:
            rest.append(turn)
    instruction = "\n\n".join(parts) if parts else None
    return instruction, rest


def _to_contents(chat_messages: list[dict[str, str]], types: Any) -> list[Any]:
    """Map TRI-BACK chat dicts to google-genai Content objects.

    Last turn must be ``user`` — Gemini 3.5 Flash-Lite rejects a trailing
    ``model`` role.
    """
    contents: list[Any] = []
    for turn in chat_messages:
        role = "model" if turn.get("role") == "assistant" else "user"
        text = turn.get("content") or ""
        contents.append(
            types.Content(role=role, parts=[types.Part.from_text(text=text)])
        )
    if contents and getattr(contents[-1], "role", None) == "model":
        raise ValueError(
            "Vertex generate_content requires the last contents turn to be role=user"
        )
    return contents


def _ensure_vertex_client() -> Any:
    global _vertex_client
    if _vertex_client is not None:
        return _vertex_client
    if not settings.vertex_project_id or not settings.vertex_location:
        raise RuntimeError(
            "TRI_BACK_VERTEX_PROJECT_ID and TRI_BACK_VERTEX_LOCATION must be set"
        )
    try:
        from google import genai
    except ImportError as exc:
        raise RuntimeError(_MISSING_GENAI) from exc
    _vertex_client = genai.Client(
        vertexai=True,
        project=settings.vertex_project_id,
        location=settings.vertex_location,
    )
    return _vertex_client


def _normalize_thinking_level(thinking_level: str | None) -> str:
    level = (thinking_level or DEFAULT_THINKING_LEVEL).strip().upper()
    if level not in _ALLOWED_THINKING:
        raise ValueError(f"unsupported thinking_level: {thinking_level!r}")
    return level


def _is_retryable(exc: BaseException) -> bool:
    status = getattr(exc, "status_code", None)
    if status is None:
        status = getattr(exc, "code", None)
    try:
        if int(status) in {429, 500, 502, 503, 504}:
            return True
    except (TypeError, ValueError):
        pass
    name = type(exc).__name__.lower()
    blob = f"{name} {exc}".lower()
    return any(
        token in blob
        for token in (
            "unavailable",
            "timeout",
            "servererror",
            "too many requests",
            "resourceexhausted",
            "503",
            "429",
        )
    )


def generate_vertex(
    messages: list[dict[str, str]],
    *,
    max_new_tokens: int,
    temperature: float = 0.2,
    thinking_level: str | None = None,
    response_mime_type: str | None = None,
    response_schema: dict[str, Any] | None = None,
) -> str:
    """Generate via google-genai on Vertex.

    ``temperature`` is accepted for call-site compatibility with the local
    backend but is not sent: Gemini 3.x ignores custom temperature/top_p.
    """
    del temperature  # unused on Gemini 3; kept in the signature for callers
    types = _genai_types()
    client = _ensure_vertex_client()
    system_instruction, chat_messages = _split_system_messages(messages)
    contents = _to_contents(chat_messages, types)
    if not contents:
        raise GenerationEmptyError("generation_empty: no user contents")

    level = _normalize_thinking_level(thinking_level)
    config_kwargs: dict[str, Any] = {
        "max_output_tokens": max_new_tokens,
        "thinking_config": types.ThinkingConfig(
            thinking_level=level,
            include_thoughts=False,
        ),
    }
    if system_instruction:
        config_kwargs["system_instruction"] = system_instruction
    if response_mime_type:
        config_kwargs["response_mime_type"] = response_mime_type
    if response_schema:
        config_kwargs["response_schema"] = response_schema
    config = types.GenerateContentConfig(**config_kwargs)

    last_exc: BaseException | None = None
    for attempt in range(_RETRY_ATTEMPTS):
        try:
            response = client.models.generate_content(
                model=settings.generator_model,
                contents=contents,
                config=config,
            )
            return _extract_response_text(response)
        except GenerationEmptyError:
            raise
        except Exception as exc:
            last_exc = exc
            if attempt + 1 < _RETRY_ATTEMPTS and _is_retryable(exc):
                _log.warning(
                    "vertex generate retry after %s: %s",
                    type(exc).__name__,
                    exc,
                )
                time.sleep(_RETRY_SLEEP_SEC)
                continue
            raise
    raise last_exc  # pragma: no cover


class GenerationEmptyError(RuntimeError):
    """Vertex (or other) generation returned no usable text."""

    def __init__(self, message: str, *, finish_reason: Any = None) -> None:
        super().__init__(message)
        self.finish_reason = finish_reason


def _finish_reason_name(finish: Any) -> str:
    if finish is None:
        return "unknown"
    name = getattr(finish, "name", None)
    if isinstance(name, str) and name:
        return name
    return str(finish)


def _is_max_tokens_finish(finish: Any) -> bool:
    name = _finish_reason_name(finish).upper()
    if "MAX_TOKEN" in name:
        return True
    # google-genai uses a string enum; older Vertex numeric MAX_TOKENS == 2.
    try:
        return int(finish) == 2
    except (TypeError, ValueError):
        return name in {"2", "FINISHREASON.MAX_TOKENS"}


def _extract_response_text(response: Any) -> str:
    """Concatenate all text parts of the first candidate.

    Thinking models can return multiple content parts (thought summary plus
    answer). Walk parts and skip those flagged as thoughts so they never leak
    into visible / JSON output.

    Empty candidates log ``finish_reason`` / safety metadata. Empty + MAX_TOKENS
    raises :class:`GenerationEmptyError` so callers treat it as generation failure
    instead of silently parsing ``""``.
    """
    candidates = getattr(response, "candidates", None) or []
    last_finish: Any = None
    saw_candidate = False
    for candidate in candidates:
        saw_candidate = True
        finish = getattr(candidate, "finish_reason", None)
        last_finish = finish
        finish_name = _finish_reason_name(finish)
        safety = getattr(candidate, "safety_ratings", None)
        content = getattr(candidate, "content", None)
        parts = getattr(content, "parts", None) or []
        texts: list[str] = []
        for part in parts:
            if getattr(part, "thought", False):
                continue
            part_text = getattr(part, "text", "") or ""
            if part_text:
                texts.append(part_text)
        if texts:
            joined = "".join(texts).strip()
            if joined:
                return joined
        _log.warning(
            "vertex candidate empty text finish_reason=%s safety=%s",
            finish_name,
            safety,
        )

    try:
        text = (response.text or "").strip()
    except (ValueError, AttributeError):
        text = ""
    if text:
        return text

    finish_name = _finish_reason_name(last_finish)
    if saw_candidate and _is_max_tokens_finish(last_finish):
        raise GenerationEmptyError(
            f"generation_empty: finish_reason={finish_name} (MAX_TOKENS)",
            finish_reason=last_finish,
        )
    if saw_candidate:
        raise GenerationEmptyError(
            f"generation_empty: finish_reason={finish_name}",
            finish_reason=last_finish,
        )
    _log.warning("vertex response had no candidates and no .text")
    raise GenerationEmptyError("generation_empty: no candidates")
