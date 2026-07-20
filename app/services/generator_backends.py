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
            "DIGIMSK_VERTEX_PROJECT_ID and DIGIMSK_VERTEX_LOCATION must be set"
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

    history, last_message = _vertex_history(messages)
    if not last_message and messages:
        last_message = messages[-1].get("content", "")
    model = GenerativeModel(settings.generator_model)
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


def _extract_response_text(response: Any) -> str:
    """Concatenate all text parts of the first candidate.

    Gemini 2.5 "thinking" models can return multiple content parts (e.g. a thought
    summary plus the answer). The SDK's ``response.text`` convenience accessor
    raises ``"Multiple content parts are not supported"`` in that case, so we walk
    the parts manually and join their text. Parts explicitly flagged as thoughts
    are skipped so they never leak into the visible / JSON output.
    """
    candidates = getattr(response, "candidates", None) or []
    for candidate in candidates:
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
            return "".join(texts).strip()
    # Single-part fallback (older responses); guarded because ``.text`` can raise.
    try:
        return (response.text or "").strip()
    except (ValueError, AttributeError):
        return ""
