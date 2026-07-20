"""Load and render the editable clinical reasoning framework.

The clinical prose lives in ``prompts/clinical_reasoning_framework.md`` (edit that
file to change the reasoning). This module fills the ``{placeholders}`` and appends
the machine-readable action protocol so the framework file can stay purely
clinical.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from app.schemas import Evidence
from app.services.agentic_graph_rag.ontology import RedFlagOntology, render_ontology_card
from app.services.agentic_graph_rag.tools import render_tool_catalog

_PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
FRAMEWORK_PATH = _PROMPTS_DIR / "clinical_reasoning_framework.md"

_HTML_COMMENT = ("<!--", "-->")

# Appended after the editable framework so the .md file stays clinical-only.
_ACTION_PROTOCOL = """

# Response protocol (machine-read — do not deviate)

Respond with exactly ONE JSON object per turn and nothing else.

To call a tool:
{{"thought": "<brief reasoning>", "action": "<tool_name>", "action_input": {{<args>}}}}

To finish with the patient-facing triage response:
{{"thought": "<brief reasoning>", "final_answer": "<triage response text>"}}

Rules:
- Output raw JSON only (no markdown fences, no prose outside the JSON).
- Call one tool at a time; wait for its OBSERVATION before the next step.
- After at most {max_steps} tool calls you MUST return a final_answer.
- action_input must be a JSON object (use {{}} when the tool takes no arguments).
"""


def _strip_leading_comment(text: str) -> str:
    """Remove the leading HTML editor-guidance comment block, if present."""
    stripped = text.lstrip()
    start, end = _HTML_COMMENT
    if stripped.startswith(start):
        idx = stripped.find(end)
        if idx != -1:
            return stripped[idx + len(end):].lstrip()
    return text


@lru_cache(maxsize=1)
def _load_framework_text() -> str:
    raw = FRAMEWORK_PATH.read_text(encoding="utf-8")
    return _strip_leading_comment(raw)


def _evidence_block(evidence: list[Evidence]) -> str:
    if not evidence:
        return "No evidence gathered yet. Use the tools to retrieve it."
    lines = [f'- [{e.source}] "{e.snippet[:280]}"' for e in evidence[:20]]
    return "\n".join(lines)


def render_system_prompt(
    *,
    ontology: RedFlagOntology,
    matched_factors: list[str],
    deterministic_conditions: list[str],
    intake_summary: str | None,
    evidence: list[Evidence],
    max_steps: int,
) -> str:
    """Fill the editable framework and append the action protocol."""
    framework = _load_framework_text()
    filled = framework.format(
        ontology_card=render_ontology_card(ontology),
        tool_catalog=render_tool_catalog(),
        matched_factors=", ".join(matched_factors) if matched_factors else "(none matched)",
        deterministic_conditions=(
            ", ".join(deterministic_conditions) if deterministic_conditions else "(none)"
        ),
        intake_summary=(intake_summary or "(no structured intake available)").strip(),
        evidence_block=_evidence_block(evidence),
    )
    return filled + _ACTION_PROTOCOL.format(max_steps=max_steps)
