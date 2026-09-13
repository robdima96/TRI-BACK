"""Cheap automated gates on patient-side text before freeze."""

from __future__ import annotations

from typing import Any

from lib.patient import flag_reply

_DUMP_RATIO = 2.5


def gate_opening(opening: str, card_opening: str) -> list[str]:
    flags = flag_reply(opening)
    if card_opening and len(opening.split()) > max(40, int(_DUMP_RATIO * len(card_opening.split()))):
        flags.append("opening_dump")
    return flags


def gate_reply(text: str) -> list[str]:
    return flag_reply(text)


def summarize_flags(turns: list[str], card: dict[str, Any]) -> dict[str, Any]:
    actor = card.get("Patient_Actor") or {}
    opening = str(actor.get("opening_complaint") or "")
    all_flags: list[dict[str, Any]] = []
    for i, turn in enumerate(turns):
        if i == 0:
            flags = gate_opening(turn, opening)
        else:
            flags = gate_reply(turn)
        if flags:
            all_flags.append({"turn_index": i, "flags": flags, "text": turn[:240]})
    return {
        "n_turns": len(turns),
        "n_flagged": len(all_flags),
        "flags": all_flags,
        "pass": len(all_flags) == 0,
    }
