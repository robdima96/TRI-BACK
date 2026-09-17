"""Span-scoped negation / uncertainty for checklist → Factor matching.

Negation is applied to the window *before* a candidate match, stopping at a
contrastive clause boundary, so mixed sentences keep their true positives:

    "my back is killing me but no bowel problems"
    → deny Bowel dysfunction, do not deny the back-pain span.
"""

from __future__ import annotations

import re
from typing import Literal

FactorPolarity = Literal["affirmed", "denied", "unknown"]

FACTOR_STATE_UNKNOWN = "unknown"
FACTOR_STATE_AFFIRMED = "affirmed"
FACTOR_STATE_DENIED = "denied"
ASKED_FACTOR_NOT_ANSWERED = "not_answered"

# Contrastive / sentence boundaries — not coordinating "and"/"or", so
# "no bladder or bowel problems" still sees the leading "no".
_CLAUSE_BOUNDARY_RE = re.compile(
    r"(?:,|;|:|\.|!|\?|"
    r"\bbut\b|\bhowever\b|\balthough\b|\bthough\b|"
    r"\bexcept\b|\bwhereas\b|\bwhile\b|\byet\b)",
    re.IGNORECASE,
)

# Check before the generic "not" cue so "I'm not sure" stays unknown.
_UNCERTAINTY_RE = re.compile(
    r"\b(?:"
    r"not\s+sure|unsure|uncertain|"
    r"don'?t\s+know|do\s+not\s+know|idk|"
    r"no\s+idea|not\s+certain"
    r")\b",
    re.IGNORECASE,
)

_NEGATION_RE = re.compile(
    r"\b(?:"
    r"no|not|never|none|neither|nor|"
    r"denies|denied|denying|"
    r"without|"
    r"nothing\s+like|"
    r"haven'?t(?:\s+had)?|hasn'?t(?:\s+had)?|"
    r"have\s+not(?:\s+had)?|has\s+not(?:\s+had)?|"
    r"don'?t|doesn'?t|didn'?t|"
    r"do\s+not|does\s+not|did\s+not|"
    r"isn'?t|aren'?t|wasn'?t|weren'?t|"
    r"can'?t|cannot|couldn'?t|"
    r"no\s+sign\s+of|no\s+history\s+of"
    r")\b",
    re.IGNORECASE,
)

_LEADING_NEG_RE = re.compile(
    r"^\s*(?:no|not|never|none|denies|denied|without|nothing\s+like)\b",
    re.IGNORECASE,
)

_WINDOW_TOKENS = 8


def _clause_prefix(text: str, start: int) -> str:
    prefix = text[: max(0, start)]
    boundaries = list(_CLAUSE_BOUNDARY_RE.finditer(prefix))
    if boundaries:
        prefix = prefix[boundaries[-1].end() :]
    return prefix


def _window(text: str) -> str:
    tokens = text.split()
    if len(tokens) <= _WINDOW_TOKENS:
        return text
    return " ".join(tokens[-_WINDOW_TOKENS:])


def polarity_for_span(text: str, start: int, end: int) -> FactorPolarity:
    """Polarity of a match at ``[start, end)`` inside ``text``.

    ``"I'm not sure"`` (and similar hedges) stay ``unknown``, never ``denied``.
    """
    if not text or start < 0 or end < start:
        return FACTOR_STATE_UNKNOWN

    clause_prefix = _clause_prefix(text, start)
    window = _window(clause_prefix)
    span = text[start:end]

    if _UNCERTAINTY_RE.search(window) or _UNCERTAINTY_RE.search(span):
        return FACTOR_STATE_UNKNOWN
    if _NEGATION_RE.search(window):
        return FACTOR_STATE_DENIED
    # Whole-item kind/label matches start at 0; "no weight loss" has no prefix.
    if start == 0 and _LEADING_NEG_RE.search(span):
        return FACTOR_STATE_DENIED
    return FACTOR_STATE_AFFIRMED


def map_span_into_message(
    item_text: str,
    start: int,
    end: int,
    source_message: str | None,
) -> tuple[str, int, int]:
    """If the checklist row is a substring of the user message, score polarity there.

    Encoder / NER rows often drop the leading "no", which is how a denial
    becomes a false affirm. The raw message still has the cue.
    """
    if not source_message or not item_text:
        return item_text, start, end
    msg = source_message
    needle = item_text.casefold()
    hay = msg.casefold()
    idx = hay.find(needle)
    if idx < 0:
        return item_text, start, end
    return msg, idx + start, idx + end


def span_has_negation(text: str, start: int, end: int) -> bool:
    return polarity_for_span(text, start, end) == FACTOR_STATE_DENIED
