"""Graph-guarded patient-question answers (Vertex, packet-constrained)."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.config import settings
from app.orchestrator.intake_slots import question_template
from app.schemas import ChecklistItem
from app.services.agentic_graph_rag.ontology import (
    get_factor_question_spec,
    load_ontology,
)
from app.services.generator import generate_from_messages, generator_model_configured
from app.services.rag.factor_matcher import match_checklist_to_factors
from app.services.rag.factor_patterns import load_factor_names
from app.services.graphrag.neo4j_config import DEFAULT_INVENTORY_PATH

_log = logging.getLogger(__name__)

CANNED_QUESTION_BRIEF = (
    "I can only use the screening topics in this tool — I'll keep going with the next question."
)

PATIENT_ANSWER_MAX_NEW_TOKENS = 512
PATIENT_ANSWER_SCHEMA: dict[str, Any] = {
    "type": "OBJECT",
    "properties": {"answer": {"type": "STRING"}},
    "required": ["answer"],
}

_FIRST_SENTENCE = re.compile(r"[^.!?]+[.!?]?")
_WS = re.compile(r"\s+")
_JSON_FENCE_RE = re.compile(
    r"```(?:json)?\s*([\s\S]*?)\s*```",
    re.IGNORECASE,
)
_SLOT_NAMES: frozenset[str] = frozenset(
    {
        "age",
        "sex",
        "comorbidities",
        "symptom_anchor",
        "symptom_duration",
        "symptom_severity",
        "symptom_quality",
        "provocative",
        "palliative",
    }
)

_ANSWER_RULES = (
    "Answer in 1-3 sentences using ONLY the knowledge-graph packet below.\n"
    "Never recommend the emergency department, urgent care, self-care, or any "
    "disposition. Never invent medications or tell the patient to do a self-exam.\n"
    "If they ask what you mean or 'like what', give 2-4 examples from the packet "
    "that match the current topic, then stop.\n"
    "Do not treat their question as answering the screening item."
)


def _first_sentence(text: str, *, limit: int = 280) -> str:
    raw = _WS.sub(" ", (text or "").strip())
    if not raw:
        return ""
    match = _FIRST_SENTENCE.search(raw)
    snippet = (match.group(0) if match else raw).strip()
    if len(snippet) > limit:
        snippet = snippet[: limit - 1].rstrip() + "…"
    return snippet


def _ontology_names() -> tuple[tuple[str, ...], tuple[str, ...]]:
    ont = load_ontology()
    factors = tuple(ont.all_factors) if ont.all_factors else load_factor_names(
        str(DEFAULT_INVENTORY_PATH)
    )
    conditions = tuple(ont.conditions or ())
    return factors, conditions


def _names_mentioned(text: str, names: tuple[str, ...]) -> list[str]:
    folded = text.casefold()
    hits: list[str] = []
    for name in sorted(names, key=len, reverse=True):
        token = name.strip()
        if len(token) < 4:
            continue
        if token.casefold() in folded:
            hits.append(token)
    return hits


def _match_question_factors(question: str) -> list[str]:
    text = (question or "").strip()
    if not text:
        return []
    names: list[str] = []
    try:
        hits = match_checklist_to_factors(
            [
                ChecklistItem(
                    text=text,
                    kind="other",
                    source="patient_question",
                    label="question",
                )
            ],
            skip_llm=True,
        )
        names.extend(h.factor_name for h in hits if h.factor_name)
    except Exception as exc:  # noqa: BLE001
        _log.debug("question brief matcher failed: %s", exc)
    factors, conditions = _ontology_names()
    names.extend(_names_mentioned(text, factors))
    names.extend(_names_mentioned(text, conditions))
    seen: set[str] = set()
    out: list[str] = []
    for name in names:
        key = name.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(name)
    return out


def _chroma_snippet(question: str) -> str | None:
    if not settings.rag_load:
        return None
    try:
        from app.services.rag.chunk_retrieval import retrieve_rag_chunk_matches
    except Exception:
        return None
    try:
        matches = retrieve_rag_chunk_matches(question, None, [], top_k=1)
    except Exception as exc:  # noqa: BLE001
        _log.debug("question brief Chroma lookup failed: %s", exc)
        return None
    if not matches:
        return None
    snippet = str(matches[0].snippet or "").strip()
    if not snippet:
        return None
    factors, conditions = _ontology_names()
    grounded = _names_mentioned(snippet, factors) or _names_mentioned(snippet, conditions)
    if not grounded:
        return None
    return _first_sentence(snippet)


def _factor_path_sentence(factor: str) -> str:
    if not settings.graphrag_load:
        return ""
    try:
        from app.services.graphrag import get_graph_client

        segs = get_graph_client().paths_for_factors([factor])
    except Exception as exc:  # noqa: BLE001
        _log.debug("question packet graph lookup failed for %s: %s", factor, exc)
        return ""
    for seg in segs:
        chunk = _first_sentence(getattr(seg, "chunk_string", "") or "")
        if chunk:
            return chunk
    return ""


def _slot_question(slot: str | None) -> str:
    if not slot or slot not in _SLOT_NAMES:
        return ""
    return question_template(slot)  # type: ignore[arg-type]


def _inventory_block() -> str:
    ont = load_ontology()
    lines = [
        f"GRAPH VERSION: {ont.graph_version}",
        "CONDITIONS: " + ", ".join(ont.conditions or ()),
        "SCREENING FACTORS (name — intent):",
    ]
    specs = ont.factor_specs or {}
    if specs:
        for name, spec in specs.items():
            intent = (spec.intent or "").strip()
            lines.append(f"- {name} — {intent}" if intent else f"- {name}")
    else:
        for name in ont.all_factors or ():
            lines.append(f"- {name}")
    return "\n".join(lines)


def _current_topic_block(
    *,
    asked_factor: str | None,
    last_asked_slot: str | None,
) -> str:
    lines: list[str] = []
    if asked_factor:
        spec = get_factor_question_spec(asked_factor)
        lines.append(f"Current graph factor: {asked_factor}")
        if spec:
            if spec.intent:
                lines.append(f"Intent: {spec.intent.strip()}")
            if spec.fallback:
                lines.append(f"Fallback question: {spec.fallback.strip()}")
            if spec.synonyms:
                lines.append("Synonyms: " + "; ".join(spec.synonyms))
        path = _factor_path_sentence(asked_factor)
        if path:
            lines.append(f"Graph evidence: {path}")
    if last_asked_slot:
        lines.append(f"Current intake slot: {last_asked_slot}")
        template = _slot_question(last_asked_slot)
        if template:
            lines.append(f"Slot question: {template}")
    if not lines:
        lines.append("Current topic: (none highlighted)")
    return "\n".join(lines)


def build_question_graph_packet(
    question_spans: list[str],
    *,
    asked_factor: str | None = None,
    last_asked_slot: str | None = None,
    query_embedding: list[float] | None = None,
) -> str:
    """Compact knowledge-graph context the generator may use to answer."""
    del query_embedding
    question = " ".join(s.strip() for s in question_spans if s and s.strip()).strip()
    parts = [
        _current_topic_block(
            asked_factor=asked_factor,
            last_asked_slot=last_asked_slot,
        ),
        _inventory_block(),
    ]
    matched = _match_question_factors(question) if question else []
    if asked_factor and asked_factor not in matched:
        matched = [asked_factor, *matched]
    extra_paths = [
        f"- {name}: {_factor_path_sentence(name)}"
        for name in matched[:4]
        if _factor_path_sentence(name)
    ]
    if extra_paths:
        parts.append("Matched factor evidence:\n" + "\n".join(extra_paths))
    chroma = _chroma_snippet(question) if question else None
    if chroma:
        parts.append(f"Chroma snippet: {chroma}")
    return "\n\n".join(parts)


def _extract_answer_json(raw: str) -> str | None:
    cleaned = (raw or "").strip()
    if not cleaned:
        return None
    fence = _JSON_FENCE_RE.search(cleaned)
    if fence:
        cleaned = fence.group(1).strip()
    payload: dict[str, Any] | None = None
    try:
        data = json.loads(cleaned)
        payload = data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start >= 0 and end > start:
            try:
                data = json.loads(cleaned[start : end + 1])
                payload = data if isinstance(data, dict) else None
            except json.JSONDecodeError:
                payload = None
    if not payload:
        return None
    answer = str(payload.get("answer") or "").strip()
    return answer or None


def _qa_prompt(question: str, packet: str) -> str:
    return (
        "You answer a patient's clarifying question during musculoskeletal screening.\n"
        f"{_ANSWER_RULES}\n\n"
        f"Patient question: {question}\n\n"
        f"Knowledge-graph packet:\n{packet}\n\n"
        'Return JSON only: {"answer": "one to three sentences"}'
    )


def answer_patient_question(
    question_spans: list[str],
    *,
    asked_factor: str | None = None,
    last_asked_slot: str | None = None,
    query_embedding: list[float] | None = None,
    packet: str | None = None,
) -> str:
    """One Vertex call constrained by the graph packet. Canned if the generator is down."""
    question = " ".join(s.strip() for s in question_spans if s and s.strip()).strip()
    if not question:
        return CANNED_QUESTION_BRIEF
    if not generator_model_configured():
        return CANNED_QUESTION_BRIEF
    graph_packet = packet or build_question_graph_packet(
        question_spans,
        asked_factor=asked_factor,
        last_asked_slot=last_asked_slot,
        query_embedding=query_embedding,
    )
    try:
        raw = generate_from_messages(
            [{"role": "user", "content": _qa_prompt(question, graph_packet)}],
            max_new_tokens=PATIENT_ANSWER_MAX_NEW_TOKENS,
            temperature=0.15,
            response_mime_type="application/json",
            response_schema=PATIENT_ANSWER_SCHEMA,
        )
    except Exception as exc:  # noqa: BLE001
        _log.warning("patient question LLM failed: %s", exc)
        return CANNED_QUESTION_BRIEF
    answer = _extract_answer_json(raw)
    return answer or CANNED_QUESTION_BRIEF


def build_question_brief(
    question_spans: list[str],
    *,
    asked_factor: str | None = None,
    last_asked_slot: str | None = None,
    query_embedding: list[float] | None = None,
) -> str:
    """Graph-guarded LLM answer; canned copy only when the generator is unavailable."""
    return answer_patient_question(
        question_spans,
        asked_factor=asked_factor,
        last_asked_slot=last_asked_slot,
        query_embedding=query_embedding,
    )
