"""Named risk flags + escalation. Matches **extracted** checklist text and the message.

Policy ids are keys in :data:`RISK_CATALOG`. Any substring match (on normalized
checklist item text and on the user message) triggers that risk for escalation
to the ER/urgent-care copy in :func:`apply_policy`.
"""

from __future__ import annotations

import re

from app.schemas import ClinicalChecklist

# Hard escalate is limited to immediately life-threatening presentations.
# Low-back red-flag clusters (CES / AAA / DVT / fracture / infection /
# malignancy) are evaluated by the disposition model from factor clusters,
# the clinical-reasoning framework, and the high-acuity priority list — not
# by this catalog.

# Catalog id -> trigger substrings (lowercase, normalized for matching)
RISK_CATALOG: dict[str, frozenset[str]] = {
    "suicide_self_harm": frozenset(
        {
            "suicide",
            "self-harm",
            "self harm",
            "kill myself",
            "end it all"
        }
    ),
    "chest_pain": frozenset({"chest pain"}),
    "respiratory_distress": frozenset(
        {
            "cannot breathe",
            "can not breathe",
            "can't breathe",
            "trouble breathing",
            "shortness of breath",
            "breathlessness",
            "gasping for breath",
            "panting",
        }
    ),
}


# processing
_WS = re.compile(r"\s+")
def _norm(s: str) -> str:
    s = s.casefold().strip()
    s = _WS.sub(" ", s)
    return s

# risk detection in message_normalized AND checklist.items
def hits_for_clinical_path(
    checklist: ClinicalChecklist, message_normalized: str
) -> list[str]:
    hits: set[str] = set()
    texts = [message_normalized, *(it.text for it in checklist.items)]
    blob = " \n".join(_norm(t) for t in texts if t)
    # scan RISK_CATALOG against the unified text blob
    for rid, terms in RISK_CATALOG.items():
        for term in terms:
            if term in blob or term in _norm(message_normalized):
                hits.add(rid)
                break
    return sorted(hits)

# policy enforcement
# maps to three ChatState fields set in policy_gate_node():
# state["escalated"] = escalated
# state["safety_reason"] = reason
# state["final_response"] = final_response
def apply_policy(
    draft_response: str,
    risk_hits: list[str],
    *,
    generator_failed: bool = False,
) -> tuple[bool, str | None, str]:
    from app.services.generator import (
        GENERATOR_SYSTEM_FAILURE_REASON,
        GENERATOR_SYSTEM_FAILURE_TEXT,
        is_generator_system_failure,
    )

    # risk escalation- overrides draft LLM response
    if risk_hits:
        reason = (
            f"Risk pattern matched: {', '.join(risk_hits)}; "
            "escalate to human or emergency care per protocol."
        )
        response = (
            "Your symptoms may need urgent in-person or emergency care. If this is a "
            "medical emergency, go to the nearest emergency department (ER) or call "
            "emergency services now."
        )
        return True, reason, response

    # Generator/backend failure must never look like a clinical ED disposition.
    # escalated is reserved for RISK_CATALOG hits; the study banner keys off it.
    if generator_failed or is_generator_system_failure(draft_response):
        return False, GENERATOR_SYSTEM_FAILURE_REASON, GENERATOR_SYSTEM_FAILURE_TEXT

    return False, None, draft_response
