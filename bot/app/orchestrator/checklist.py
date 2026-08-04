"""Clinical checklist merge (session + current-turn encoder output)."""

from app.schemas import ChecklistItem


def merge_checklist_items(
    prior: list[dict[str, str]],
    current_items: list[ChecklistItem],
) -> list[dict[str, str]]:
    """Dedupe by (text, kind, source, label); append new items from the current turn."""

    def key(d: dict[str, str]) -> tuple[str, str, str, str]: # two items considered duplicate if all four fields match
        return (
            d.get("text", ""),
            d.get("kind", ""),
            d.get("source", ""),
            d.get("label", ""),
        )

    seen = {key(i) for i in prior}
    out: list[dict[str, str]] = [dict(x) for x in prior]
    for it in current_items: # append only new items from the current turn
        d = it.model_dump()
        if key(d) not in seen:
            seen.add(key(d))
            out.append(d)
    return out
