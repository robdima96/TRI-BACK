"""Bounded, auditable ReAct-style disposition agent over local graph/RAG tools.

The agent is deliberately backend-agnostic: it drives the same
``generate_from_messages`` used by the deterministic path (local Mistral or
Vertex Gemini), exchanging a strict one-JSON-object-per-turn protocol so it works
without native tool-calling. Determinism is relaxed (the agent chooses which
graph/RAG tools to call and how to weigh clusters), but hallucination is bounded
by (a) read-only tools over the ground-truth graph, (b) ontology-validated
arguments, and (c) a full :class:`AgentTrace` of every step.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.schemas import Evidence
from app.services.agentic_graph_rag.ontology import RedFlagOntology
from app.services.agentic_graph_rag.prompt_template import render_system_prompt
from app.services.agentic_graph_rag.schemas import (
    AgentStep,
    AgentTrace,
    ToolCall,
    ToolResult,
)
from app.services.agentic_graph_rag.tools import ToolContext, invoke_tool, tool_names

_log = logging.getLogger(__name__)

# NOTE: Gemini 2.5 "thinking" tokens count against max_output_tokens, so these
# caps must cover the model's internal reasoning budget plus the visible output.
# Under-sized caps surface as Vertex "Finish reason: 2" (MAX_TOKENS) errors that
# return empty text. Raised from 512/1024 after observing agent-step failures.
_TOOL_STEP_MAX_TOKENS = 2048
_FINAL_MAX_TOKENS = 4096
_TEMPERATURE = 0.2

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)\s*```", re.IGNORECASE)


def _first_json_object(text: str) -> dict[str, Any] | None:
    """Tolerantly extract the first JSON object from model output."""
    if not text:
        return None
    fence = _JSON_FENCE_RE.search(text)
    candidates: list[str] = []
    if fence:
        candidates.append(fence.group(1))
    # Brace-matched fallback scan.
    depth = 0
    start = -1
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            if depth > 0:
                depth -= 1
                if depth == 0 and start != -1:
                    candidates.append(text[start : i + 1])
    for cand in candidates:
        try:
            obj = json.loads(cand)
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            continue
    return None


def _accumulate(trace: AgentTrace, result: ToolResult) -> None:
    for f in result.factors:
        if f not in trace.used_factors:
            trace.used_factors.append(f)
    for c in result.conditions:
        if c not in trace.used_conditions:
            trace.used_conditions.append(c)
    for cid in result.chunk_ids:
        if cid not in trace.used_chunk_ids:
            trace.used_chunk_ids.append(cid)


def run_disposition_agent(
    *,
    query: str,
    checklist: list[dict[str, str]],
    chunk_matches: list,
    ontology: RedFlagOntology,
    matched_factors: list[str],
    deterministic_conditions: list[str],
    baseline_evidence: list[Evidence],
    intake_summary: str | None,
    conversation_history: list[dict[str, str]] | None,
    max_steps: int,
) -> tuple[str | None, AgentTrace]:
    """Run the agent loop.

    Returns ``(final_text_or_None, trace)``. ``None`` final text signals the
    caller to fall back to the deterministic draft.
    """
    from app.services.generator import extract_answer_text, generate_from_messages

    trace = AgentTrace(
        max_steps=max_steps,
        available_tools=tool_names(),
        deterministic_conditions=list(deterministic_conditions),
    )

    ctx = ToolContext(
        checklist=checklist,
        chunk_matches=chunk_matches,
        ontology=ontology,
        query=query,
    )

    system_prompt = render_system_prompt(
        ontology=ontology,
        matched_factors=matched_factors,
        deterministic_conditions=deterministic_conditions,
        intake_summary=intake_summary,
        evidence=baseline_evidence,
        max_steps=max_steps,
    )

    messages: list[dict[str, str]] = []
    for turn in conversation_history or []:
        role = turn.get("role", "user")
        if role not in ("user", "assistant"):
            role = "user"
        messages.append({"role": role, "content": turn.get("content", "")})
    messages.append(
        {
            "role": "user",
            "content": (
                system_prompt
                + f"\n\nCurrent user message: {query}\n\n"
                + "Begin. Inspect the graph with a tool, then reason, "
                + "then return your final_answer."
            ),
        }
    )

    parse_failures = 0
    for step_idx in range(1, max_steps + 1):
        try:
            raw = generate_from_messages(
                messages,
                max_new_tokens=_TOOL_STEP_MAX_TOKENS,
                temperature=_TEMPERATURE,
            )
        except Exception as exc:  # pragma: no cover - backend failure
            _log.exception("agent generation failed: %s", exc)
            trace.status = "error"
            trace.stop_reason = f"generation_error: {exc}"
            return None, trace

        obj = _first_json_object(raw)
        thought = (obj or {}).get("thought") if isinstance(obj, dict) else None

        if obj is None:
            parse_failures += 1
            trace.steps.append(
                AgentStep(step=step_idx, thought=None, raw=raw, result=None)
            )
            if parse_failures >= 2:
                trace.status = "fallback"
                trace.stop_reason = "unparseable_output"
                return None, trace
            messages.append({"role": "assistant", "content": raw})
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "Your last message was not valid JSON. Respond with exactly "
                        "one JSON object using either 'action'/'action_input' or "
                        "'final_answer'."
                    ),
                }
            )
            continue

        if "final_answer" in obj:
            final = str(obj.get("final_answer") or "").strip()
            final = extract_answer_text(final)
            trace.steps.append(AgentStep(step=step_idx, thought=thought, raw=raw))
            trace.steps_taken = step_idx
            if not final:
                trace.status = "fallback"
                trace.stop_reason = "empty_final_answer"
                return None, trace
            trace.status = "ok"
            trace.stop_reason = "final_answer"
            return final, trace

        action = obj.get("action")
        action_input = obj.get("action_input")
        if not isinstance(action_input, dict):
            action_input = {}
        if not isinstance(action, str) or not action:
            parse_failures += 1
            trace.steps.append(AgentStep(step=step_idx, thought=thought, raw=raw))
            messages.append({"role": "assistant", "content": raw})
            messages.append(
                {
                    "role": "user",
                    "content": "Provide a valid 'action' (tool name) or a 'final_answer'.",
                }
            )
            if parse_failures >= 2:
                trace.status = "fallback"
                trace.stop_reason = "no_valid_action"
                return None, trace
            continue

        result = invoke_tool(action, action_input, ctx)
        _accumulate(trace, result)
        trace.steps.append(
            AgentStep(
                step=step_idx,
                thought=thought,
                action=ToolCall(name=action, arguments=action_input),
                result=result,
                raw=raw,
            )
        )
        trace.steps_taken = step_idx
        messages.append({"role": "assistant", "content": raw})
        messages.append(
            {"role": "user", "content": f"OBSERVATION ({action}): {result.observation}"}
        )

    # Ran out of steps without a final answer: force one grounded final turn.
    messages.append(
        {
            "role": "user",
            "content": (
                "Step budget reached. Using only the observations above, respond "
                'now with exactly one JSON object: {"final_answer": "<triage '
                'response>"}. Do not call any more tools.'
            ),
        }
    )
    try:
        raw = generate_from_messages(
            messages, max_new_tokens=_FINAL_MAX_TOKENS, temperature=_TEMPERATURE
        )
    except Exception as exc:  # pragma: no cover - backend failure
        _log.exception("agent final generation failed: %s", exc)
        trace.status = "error"
        trace.stop_reason = f"final_generation_error: {exc}"
        return None, trace

    obj = _first_json_object(raw)
    final = ""
    if isinstance(obj, dict) and "final_answer" in obj:
        final = str(obj.get("final_answer") or "").strip()
    else:
        final = extract_answer_text(raw)
    final = extract_answer_text(final)
    if not final:
        trace.status = "fallback"
        trace.stop_reason = "no_final_after_budget"
        return None, trace
    trace.status = "ok"
    trace.stop_reason = "forced_final_answer"
    return final, trace
