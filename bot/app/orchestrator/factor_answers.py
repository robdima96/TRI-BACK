"""Credit the reply to a graph factor question into ``factor_states``.

A bare "no" is a denial here. The same string is a non-answer to a slot
question (``slot_answers._EMPTY_ANSWER``) and must not reach
``credit_asked_slot_answer``.
"""

from __future__ import annotations

import re

from app.services.agentic_graph_rag.ontology import (
    FactorQuestionSpec,
    get_factor_question_spec,
)
from app.services.rag.factor_polarity import (
    FACTOR_STATE_AFFIRMED,
    FACTOR_STATE_DENIED,
    FACTOR_STATE_UNKNOWN,
    FactorPolarity,
    polarity_for_span,
)

_UNCERTAINTY = re.compile(
    r"^\s*(?:i\s+don'?t\s+know|idk|unsure|not\s+sure|n/?a|"
    r"no\s+idea|not\s+certain|\?+)\s*$",
    re.I,
)
_BARE_YES = re.compile(
    r"^\s*(?:yes|yeah|yep|yup|yea|y|i have|i did|i do|"
    r"a little|a bit|sometimes|i think so)\b",
    re.I,
)
_BARE_NO = re.compile(
    r"^\s*(?:no|nope|nah|n|not really|i haven'?t|i don'?t|never|none)\b",
    re.I,
)


def _synonym_span(message: str, spec: FactorQuestionSpec) -> tuple[int, int] | None:
    hay = message.casefold()
    needles = (spec.factor, *spec.synonyms)
    best: tuple[int, int] | None = None
    for needle in needles:
        n = needle.strip().casefold()
        if not n:
            continue
        idx = hay.find(n)
        if idx >= 0 and (best is None or idx < best[0]):
            best = (idx, idx + len(n))
    return best


def polarity_for_factor_reply(
    message: str,
    spec: FactorQuestionSpec,
) -> FactorPolarity:
    """Interpret the patient's reply relative to the factor just asked."""
    text = (message or "").strip()
    if not text:
        return FACTOR_STATE_UNKNOWN
    if _UNCERTAINTY.match(text):
        return FACTOR_STATE_UNKNOWN
    span = _synonym_span(text, spec)
    if span is not None:
        return polarity_for_span(text, span[0], span[1])
    if _BARE_NO.match(text):
        return FACTOR_STATE_DENIED
    if _BARE_YES.match(text):
        return FACTOR_STATE_AFFIRMED
    # Whole-message polarity only when the wording is a short hedge, not a
    # volunteered finding about something else.
    if len(text.split()) <= 6:
        return polarity_for_span(text, 0, len(text))
    return FACTOR_STATE_UNKNOWN


def credit_asked_factor_answer(
    *,
    message: str,
    asked_factor: str | None,
    factor_states: dict[str, str] | None,
) -> dict[str, str]:
    """Write affirmed|denied|unknown for ``asked_factor`` from this turn's reply.

    Does not add checklist rows (a "no" must not become matchable text).
    Overwrites this factor's prior state so a bare yes/no wins over matcher noise.
    """
    out = dict(factor_states or {})
    if not asked_factor:
        return out
    spec = get_factor_question_spec(asked_factor)
    if spec is None or not spec.askable:
        return out
    polarity = polarity_for_factor_reply(message, spec)
    if polarity == FACTOR_STATE_UNKNOWN:
        # Don't clear a sticky affirmed/denied with "not sure".
        out.setdefault(asked_factor, FACTOR_STATE_UNKNOWN)
    else:
        out[asked_factor] = polarity
    return out
