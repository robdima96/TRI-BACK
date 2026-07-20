"""LLM-driven intake follow-up questions from checklist + chat history."""

from __future__ import annotations

import logging
import re

from app.orchestrator.coverage import coverage_intake_summary
from app.orchestrator.intake_models import CoverageReport, SlotName
from app.orchestrator.intake_slots import (
    question_template,
    slot_intake_brief,
    symptom_display_name,
)
from app.services.generator import generate_from_messages, generator_model_configured

_log = logging.getLogger(__name__)

INTAKE_MAX_NEW_TOKENS = 4096
_MIN_QUESTION_WORDS = 5

_OFF_TOPIC_RE = re.compile(
    r"\b("
    r"medication|medications|other medical condition|other health condition|"
    r"comorbid|chronic condition|take any pills"
    r")\b",
    re.I,
)

_THINKING_TAG_RE = re.compile(r"<thinking>.*?</thinking>", re.DOTALL | re.IGNORECASE)
_ANSWER_TAG_RE = re.compile(r"<answer>\s*(.*?)\s*</answer>", re.DOTALL | re.IGNORECASE)
_INCOMPLETE_FRAGMENT_RE = re.compile(
    r"^(?:how would|how could|what is the|could you describe how|can you describe how|"
    r"would you describe how|how would you|could you tell me how)\s*\??$",
    re.I,
)


def _strip_intake_scaffolding(text: str) -> str:
    """Normalize model output for intake (one plain question; no CoT scaffolding)."""
    cleaned = text.strip()
    if not cleaned:
        return ""
    cleaned = _THINKING_TAG_RE.sub("", cleaned).strip()
    answer_match = _ANSWER_TAG_RE.search(cleaned)
    if answer_match:
        cleaned = answer_match.group(1).strip()
    return cleaned


def _normalize_question_line(line: str) -> str:
    return line.strip().lstrip("-•*0123456789.) ")


def _question_looks_complete(question: str) -> bool:
    """Reject truncated fragments the model emits when output budget is tight."""
    q = question.strip()
    if not q.endswith("?"):
        return False
    if _INCOMPLETE_FRAGMENT_RE.match(q):
        return False
    words = [w for w in re.split(r"\s+", q.rstrip("?")) if w]
    return len(words) >= _MIN_QUESTION_WORDS


def _sanitize_question(text: str) -> str:
    """
    Extract one complete intake question from model text.

    Intake prompts ask for a single question sentence (no CoT). Prefer the longest
    plausible question line so a short preamble line cannot win over the real question.
    """
    cleaned = _strip_intake_scaffolding(text)
    if not cleaned:
        return ""

    lines = [_normalize_question_line(line) for line in cleaned.splitlines()]
    lines = [line for line in lines if line]
    candidates = list(lines)
    if len(lines) <= 1:
        collapsed = " ".join(cleaned.split())
        if collapsed and collapsed not in candidates:
            candidates.append(collapsed)

    question_lines = [c for c in candidates if c.endswith("?")]
    if question_lines:
        best = max(question_lines, key=len)
        if _question_looks_complete(best):
            return best

    partial = _normalize_question_line(candidates[0]) if candidates else ""
    if partial and not partial.endswith("?"):
        _log.debug("intake LLM partial output (no trailing ?): %r", partial[:120])
    return ""


def _format_checklist_block(checklist: list[dict[str, str]]) -> str:
    if not checklist:
        return "(empty — nothing extracted yet)"
    lines: list[str] = []
    for i, row in enumerate(checklist, 1):
        lines.append(
            f"  {i}. text={row.get('text', '')!r}  "
            f"kind={row.get('kind', '')!r}  "
            f"source={row.get('source', '')!r}  "
            f"label={row.get('label', '')!r}"
        )
    return "\n".join(lines)


def _question_matches_slot(question: str, slot: SlotName) -> bool:
    if not question.strip():
        return False
    if slot == "comorbidities":
        return True
    if _OFF_TOPIC_RE.search(question):
        return False
    return True


def _build_intake_messages(
    *,
    checklist: list[dict[str, str]],
    conversation_history: list[dict[str, str]],
    coverage: CoverageReport,
    latest_user_message: str,
    slot: SlotName,
    display_name: str,
    base_question: str,
) -> list[dict[str, str]]:
    topic = slot_intake_brief(slot, display_name=display_name)
    user_block = (
        "Rephrase ONE clinical intake question for the patient.\n\n"
        f"REQUIRED TOPIC (do not change): {topic}\n"
        f"BASE QUESTION (keep this meaning): {base_question}\n\n"
        "Use the transcript and checklist only for context and wording — "
        "do not introduce a different topic.\n"
        "Rules:\n"
        "- Output exactly one complete question sentence ending with ?.\n"
        "- Output only the question — no reasoning, preamble, lists, or tags.\n"
        "- Do not use <thinking> or <answer> tags.\n"
        "- Stay focused on the required topic.\n"
        "- Do not ask about medications or unrelated medical conditions "
        "unless the base question already does.\n"
        "- Do not give triage advice or a diagnosis.\n\n"
        f"Coverage summary:\n{coverage_intake_summary(coverage)}\n\n"
        f"Clinical checklist:\n{_format_checklist_block(checklist)}\n\n"
        f"Latest patient message: {latest_user_message.strip() or '(none)'}\n"
    )
    messages: list[dict[str, str]] = []
    for turn in conversation_history:
        role = turn.get("role", "user")
        if role not in ("user", "assistant"):
            role = "user"
        messages.append({"role": role, "content": turn.get("content", "")})
    messages.append({"role": "user", "content": user_block})
    return messages


def generate_intake_question(
    *,
    checklist: list[dict[str, str]],
    conversation_history: list[dict[str, str]],
    coverage: CoverageReport,
    latest_user_message: str,
    slot: SlotName,
    active_symptom_id: str | None,
) -> tuple[str, str]:
    """
    Return ``(question_text, reason)`` using the local generator LLM.

    The planner picks the target slot; the LLM rephrases the template question
    conversationally. Falls back to the template when the model is unavailable,
    incomplete, or drifts off-topic.
    """
    instances = coverage.get("symptom_instances") or []
    display = symptom_display_name(instances, active_symptom_id)
    fallback = question_template(slot, display_name=display)
    reason = f"llm_intake:missing:{slot}"
    if active_symptom_id:
        reason = f"{reason}:symptom={active_symptom_id}"

    if not generator_model_configured():
        _log.warning("intake LLM unavailable; using template for slot %s", slot)
        return fallback, f"template_fallback:{reason}"

    try:
        messages = _build_intake_messages(
            checklist=checklist,
            conversation_history=conversation_history,
            coverage=coverage,
            latest_user_message=latest_user_message,
            slot=slot,
            display_name=display,
            base_question=fallback,
        )
        raw = generate_from_messages(
            messages,
            max_new_tokens=INTAKE_MAX_NEW_TOKENS,
            temperature=0.25,
        )
        question = _sanitize_question(raw)
        if not question or not _question_matches_slot(question, slot):
            detail = question[:80] if question else raw[:80]
            _log.info(
                "intake LLM unusable for slot %s (%r); using template",
                slot,
                detail,
            )
            return fallback, f"template_fallback:{reason}"
        return question, reason
    except Exception as exc:
        _log.exception("intake LLM failed: %s", exc)
        return fallback, f"template_fallback:{reason}"
