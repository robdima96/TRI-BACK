"""Named risk flags + escalation. Matches **extracted** checklist text and the message.

Policy ids are keys in :data:`RISK_CATALOG`. Any substring match (on normalized
checklist item text and on the user message) triggers that risk for escalation
to the ER/urgent-care copy in :func:`apply_policy`.
"""

from __future__ import annotations

import re

from app.schemas import ClinicalChecklist

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
) -> tuple[bool, str | None, str]:
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
    return False, None, draft_response
