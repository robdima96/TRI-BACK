"""Remote and local text generation backends for ``generator.py``."""

from __future__ import annotations

import logging
from typing import Any

from app.config import settings

_log = logging.getLogger(__name__)

_vertex_initialized = False


def _vertex_history(messages: list[dict[str, str]]) -> tuple[list[Any], str]:
    try:
        from vertexai.generative_models import Content, Part
    except ImportError as exc:
        raise RuntimeError(
            "google-cloud-aiplatform not installed; pip install -e '.[generator-api]'"
        ) from exc

    if not messages:
        return [], ""
    history: list[Content] = []
    for turn in messages[:-1]:
        role = "model" if turn.get("role") == "assistant" else "user"
        history.append(
            Content(role=role, parts=[Part.from_text(turn.get("content", ""))])
        )
    last = messages[-1].get("content", "")
    return history, last


def _ensure_vertex() -> None:
    global _vertex_initialized
    if _vertex_initialized:
        return
    if not settings.vertex_project_id or not settings.vertex_location:
        raise RuntimeError(
            "TRI_BACK_VERTEX_PROJECT_ID and TRI_BACK_VERTEX_LOCATION must be set"
        )
    try:
        import vertexai
    except ImportError as exc:
        raise RuntimeError(
            "google-cloud-aiplatform not installed; pip install -e '.[generator-api]'"
        ) from exc
    vertexai.init(
        project=settings.vertex_project_id,
        location=settings.vertex_location,
    )
    _vertex_initialized = True


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


def generate_vertex(
    messages: list[dict[str, str]],
    *,
    max_new_tokens: int,
    temperature: float,
) -> str:
    _ensure_vertex()
    try:
        from vertexai.generative_models import GenerationConfig, GenerativeModel
    except ImportError as exc:
        raise RuntimeError(
            "google-cloud-aiplatform not installed; pip install -e '.[generator-api]'"
        ) from exc

    system_instruction, chat_messages = _split_system_messages(messages)
    history, last_message = _vertex_history(chat_messages)
    if not last_message and chat_messages:
        last_message = chat_messages[-1].get("content", "")
    model_kwargs: dict[str, Any] = {}
    if system_instruction:
        model_kwargs["system_instruction"] = system_instruction
    model = GenerativeModel(settings.generator_model, **model_kwargs)
    generation_config = GenerationConfig(
        max_output_tokens=max_new_tokens,
        temperature=temperature,
        top_p=0.9,
    )
    if history:
        chat = model.start_chat(history=history)
        response = chat.send_message(
            last_message,
            generation_config=generation_config,
        )
    else:
        response = model.generate_content(
            last_message,
            generation_config=generation_config,
        )
    return _extract_response_text(response)


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
    # Vertex enum: FinishReason.MAX_TOKENS == 2
    try:
        return int(finish) == 2
    except (TypeError, ValueError):
        return name in {"2", "FINISHREASON.MAX_TOKENS"}


def _extract_response_text(response: Any) -> str:
    """Concatenate all text parts of the first candidate.

    Gemini 2.5 "thinking" models can return multiple content parts (e.g. a thought
    summary plus the answer). The SDK's ``response.text`` convenience accessor
    raises ``"Multiple content parts are not supported"`` in that case, so we walk
    the parts manually and join their text. Parts explicitly flagged as thoughts
    are skipped so they never leak into the visible / JSON output.

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

    # Single-part fallback (older responses); guarded because ``.text`` can raise.
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
