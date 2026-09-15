"""Presentation adapters keyed by effective group_id."""

from __future__ import annotations

import re

from tri_back_study_app.adapters.base import ChatTurnResult
from tri_back_study_app.adapters.http_client import call_chat_api
from tri_back_study_app.graph import BotTraversalClient, reasoning_text
from tri_back_study_app.graph.cytoscape_builder import arm3_keyed_json
from tri_back_study_app.models.chat_types import filter_display_citations

_SENTENCE_SPLIT = re.compile(r"(?<!\d)(?<=[.!?])\s+")
_NUMBERED_ITEM = re.compile(r"^\s*\d+\.\s")
_INSTRUCTION_HEADING = re.compile(
    r"accuracy|graph disposition brief|no diagnosis/prescription|"
    r"step-by-step derivation|strictly follow",
    re.I,
)
_TRIAGE_SPEECH = re.compile(
    r"\b("
    r"emergency department|emergency room|\bed\b|urgent care|self-care|"
    r"see a (?:doctor|clinician|physician)|go to (?:the )?(?:er|hospital)|"
    r"in-person assessment"
    r")\b",
    re.I,
)


def simplify_disposition(text: str, *, max_sentences: int = 2) -> str:
    """Arm 1: keep the triage recommendation, drop elongated explanation.

    Numbered-list periods (``2. ``) are not sentence boundaries. Instruction
    headings and tiny fragments are skipped so a leaked CoT cannot collapse to
    `` `. 2. ``. If nothing usable remains, keep the original text.
    """
    cleaned = (text or "").strip()
    if not cleaned:
        return cleaned
    parts = [p.strip() for p in _SENTENCE_SPLIT.split(cleaned) if p.strip()]
    usable: list[str] = []
    for part in parts:
        if _NUMBERED_ITEM.match(part):
            continue
        if len(part) <= 3 and not _TRIAGE_SPEECH.search(part):
            continue
        if _INSTRUCTION_HEADING.search(part) and not _TRIAGE_SPEECH.search(part):
            continue
        usable.append(part)
    if not usable:
        return cleaned
    chosen = usable[:max_sentences]
    return " ".join(chosen)


class PresentationAdapter:
    def __init__(self, group_id: int) -> None:
        self.group_id = group_id
        self._traversal = BotTraversalClient()

    async def send_message(self, session_id: str, message: str) -> ChatTurnResult:
        result = await call_chat_api(session_id, message)
        # Keep full citation inventory on graph_traversal / bot payload; UI
        # messages get literature-facing chips only.
        result.citations = filter_display_citations(result.citations)
        trace = self._traversal.from_chat_response(result)

        # Arm 1: simplified disposition text only (no CoT, no graph).
        # Arm 2: disposition + chain-of-thought narrative from traversal.
        # Arm 3: disposition + Cytoscape / traversal graph panel.
        if self.group_id == 1:
            if trace or result.coverage_ready or result.escalated:
                result.response = simplify_disposition(result.response)
            result.reasoning_text = None
            result.graph_json = None
            result.has_graph = False
        elif self.group_id == 2:
            if trace:
                result.reasoning_text = reasoning_text(trace) or None
            else:
                result.reasoning_text = None
            result.graph_json = None
            result.has_graph = False
        elif self.group_id == 3:
            result.reasoning_text = None
            if result.question_mode:
                result.graph_json = None
                result.has_graph = False
            else:
                intake_trace = self._traversal.intake_from_chat_response(result)
                payload = arm3_keyed_json(intake=intake_trace, disposition=trace)
                result.graph_json = payload
                result.has_graph = bool(payload)
        else:
            result.reasoning_text = None
            result.graph_json = None
            result.has_graph = False
        return result


def get_presentation_adapter(group_id: int) -> PresentationAdapter:
    arm = group_id if group_id in (1, 2, 3) else 1
    return PresentationAdapter(arm)
