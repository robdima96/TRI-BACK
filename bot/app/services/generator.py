"""Draft responses via local Mistral or Vertex Gemini backends."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from app.config import settings
from app.schemas import Evidence
from app.services import generator_backends
from app.services.vertex_auth import vertex_adc_status

_log = logging.getLogger(__name__)

# Sized to cover Gemini 2.5 thinking tokens + visible output (see agent.py note).
DISPOSITION_MAX_NEW_TOKENS = 4096

# Non-clinical copy when the generator backend is down. Must never look like a
# triage recommendation. Policy gate marks escalated + system_failure reason.
GENERATOR_SYSTEM_FAILURE_TEXT = (
    "I'm temporarily unable to generate a recommendation due to a system error. "
    "Please try again shortly. If your symptoms feel urgent or are getting worse, "
    "contact a clinician or emergency services directly."
)
GENERATOR_SYSTEM_FAILURE_REASON = "system_failure:generator_unavailable"

_tok_gen: Any = None  # tokenizer
_mdl_gen: Any = None  # model

# define chatbot role, constraints, and behavior
# CoT: Chain of Thought added
_SYSTEM_INSTRUCTION = (
    "You are a helpful, respectful, musculoskeletal health information assistant. "
    "To ensure absolute accuracy, you must think through problems step-by-step before providing a final answer"
    "Structure your response into two distinct sections:"
    "1. <thinking>"
    "Break down the user's request."
    "List the constraints, variables, or core logic rules."
    "Show your step-by-step work, calculations, or logical deductions."
    "Challenge your own assumptions and check for errors."
    "2. <answer>"
    "State the clear, direct final answer based strictly on the reasoning inside the <thinking> block."
    "Never skip the <thinking> process, even for simple-looking requests."
    "Keep the <thinking> section focused purely on logic and calculation and the Evidence provided."
    "If the evidence does not cover the question, say you don't have enough information. "
    "Never diagnose. Never prescribe. "
    "For disposition turns, give a clear triage recommendation on whether the patient should "
    "attend the emergency department (ED) now, seek urgent or routine in-person care, or "
    "manage with self-care while monitoring for red flags. "
    "For all queries, keep in mind that your role is to support the individual's "
    "capacity to cope with life autonomously — not to provide a formal diagnosis or treatment. "
    ""
)

_ANSWER_TAG_RE = re.compile(r"<answer>\s*(.*?)\s*</answer>", re.DOTALL | re.IGNORECASE)


def _generator_path_looks_valid(generator_dir: str) -> bool:
    root = Path(generator_dir)
    if not root.is_dir():
        return False
    return any(root.glob("*.safetensors")) or (root / "model.safetensors").is_file()


def generator_backend() -> str:
    """Active backend: ``local`` or ``vertex``."""
    return settings.generator_backend


def generator_model_configured() -> bool:
    """True when the selected backend has the credentials or weights it needs."""
    backend = generator_backend()
    if backend == "local":
        return _generator_path_looks_valid(settings.generator_model_dir)
    if backend == "vertex":
        if not (settings.vertex_project_id and settings.vertex_location):
            return False
        adc_ok, _ = vertex_adc_status()
        return adc_ok
    return False


def generator_status_detail() -> str:
    """Human-readable generator readiness for ``/ready``."""
    backend = generator_backend()
    if backend == "local":
        if _generator_path_looks_valid(settings.generator_model_dir):
            return f"ok (local: {settings.generator_model_dir})"
        return f"no safetensors under {settings.generator_model_dir}"
    if backend == "vertex":
        if not (settings.vertex_project_id and settings.vertex_location):
            return "DIGIMSK_VERTEX_PROJECT_ID or DIGIMSK_VERTEX_LOCATION not set"
        adc_ok, adc_detail = vertex_adc_status()
        base = (
            f"vertex: {settings.generator_model} @ "
            f"{settings.vertex_project_id}/{settings.vertex_location}"
        )
        if adc_ok:
            return f"ok ({base}; {adc_detail})"
        return f"{adc_detail} [{base}]"
    return f"unknown backend {backend!r}"


def extract_answer_text(text: str) -> str:
    """Prefer content inside ``<answer>`` when the model uses CoT tags."""
    match = _ANSWER_TAG_RE.search(text)
    if match:
        return match.group(1).strip()
    return text.strip()


def _generate_local_messages(
    messages: list[dict[str, str]],
    *,
    max_new_tokens: int,
    temperature: float,
) -> str:
    if not _ensure_generator(settings.generator_model_dir):
        raise RuntimeError(f"generator not available at {settings.generator_model_dir}")
    import torch

    assert _tok_gen is not None and _mdl_gen is not None
    prompt = _tok_gen.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=True
    )
    inputs = _tok_gen(prompt, return_tensors="pt").to(_mdl_gen.device)
    with torch.no_grad():
        output_ids = _mdl_gen.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            do_sample=True,
            temperature=temperature,
            top_p=0.9,
        )
    new_tokens = output_ids[0][inputs["input_ids"].shape[1] :]
    return _tok_gen.decode(new_tokens, skip_special_tokens=True).strip()


def generate_from_messages(
    messages: list[dict[str, str]],
    *,
    max_new_tokens: int = 500,
    temperature: float = 0.2,
) -> str:
    """Run the configured generator backend on a pre-built chat message list."""
    backend = generator_backend()
    if backend == "local":
        return _generate_local_messages(
            messages,
            max_new_tokens=max_new_tokens,
            temperature=temperature,
        )
    if backend == "vertex":
        return generator_backends.generate_vertex(
            messages,
            max_new_tokens=max_new_tokens,
            temperature=temperature,
        )
    raise RuntimeError(
        f"unsupported DIGIMSK_GENERATOR_BACKEND: {backend!r} "
        "(supported: local, vertex)"
    )


# checks that safetensor LLM files are available
def _ensure_generator(generator_dir: str) -> bool:
    global _tok_gen, _mdl_gen
    if _mdl_gen is not None and _tok_gen is not None:
        return True
    root = Path(generator_dir)
    if not root.is_dir():
        return False
    st = any(root.glob("*.safetensors")) or (root / "model.safetensors").is_file()
    if not st:
        return False
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    p = str(root.resolve())
    _tok_gen = AutoTokenizer.from_pretrained(p, local_files_only=True)
    _mdl_gen = AutoModelForCausalLM.from_pretrained(
        p,
        torch_dtype=torch.float16,
        device_map="auto",
    )
    return True


def _build_messages_for_chat(
    query: str,
    evidence: list[dict[str, Any]],
    conversation_history: list[dict[str, str]] | None,
    *,
    intake_summary: str | None = None,
) -> list[dict[str, str]]:
    lines = [f"- [{e.get('source', '')}] \"{e.get('snippet', '')}\"" for e in evidence]
    block = "\n".join(lines) if lines else "No evidence available."
    intake_block = ""
    if intake_summary and intake_summary.strip():
        intake_block = f"Structured intake (from conversation):\n{intake_summary.strip()}\n\n"
    current_content = (
        f"{_SYSTEM_INSTRUCTION}\n\n"
        f"{intake_block}"
        f"Evidence:\n{block}\n\n"
        f"Current user message: {query}"
    )
    messages: list[dict[str, str]] = []
    for turn in conversation_history or []:
        role = turn.get("role", "user")
        content = turn.get("content", "")
        if role not in ("user", "assistant"):
            role = "user"
        messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": current_content})
    return messages


def is_generator_system_failure(text: str | None) -> bool:
    return (text or "").strip() == GENERATOR_SYSTEM_FAILURE_TEXT


def generate_response(
    query: str,
    evidence: list[Evidence],
    *,
    conversation_history: list[dict[str, str]] | None = None,
    intake_summary: str | None = None,
) -> str:
    """Generate a draft with the configured backend, or a system-failure stub."""
    if not generator_model_configured():
        return _generator_unavailable_stub(query, evidence, conversation_history)

    try:
        ev: list[dict[str, Any]] = [e.model_dump() for e in evidence]
        messages = _build_messages_for_chat(
            query, ev, conversation_history, intake_summary=intake_summary
        )
        raw = generate_from_messages(
            messages,
            max_new_tokens=DISPOSITION_MAX_NEW_TOKENS,
            temperature=0.2,
        )
        text = extract_answer_text(raw)
        if not text.strip():
            _log.warning("generator returned empty text; treating as system failure")
            return _generator_unavailable_stub(query, evidence, conversation_history)
        return text
    except Exception as e:
        _log.exception("%s generate failed: %s", generator_backend(), e)
        return _generator_unavailable_stub(query, evidence, conversation_history)


def _generator_unavailable_stub(
    query: str,
    evidence: list[Evidence],
    conversation_history: list[dict[str, str]] | None,
) -> str:
    source_label = evidence[0].source if evidence else "no-source"
    prior_turns = len(conversation_history) if conversation_history else 0
    _log.warning(
        "generator unavailable; emitting system-failure copy "
        "(source=%r, query=%r, prior_turns=%s)",
        source_label,
        query[:120],
        prior_turns,
    )
    return GENERATOR_SYSTEM_FAILURE_TEXT
