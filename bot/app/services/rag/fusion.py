"""Merge factor matching and chunk seeds for graph traversal."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.schemas import ChecklistItem, ChecklistItemDump, ChunkMatch
from app.services.graphrag.schemas import FactorMatch, GraphTraversalTrace
from app.services.rag.factor_matcher import (
    affirmed_factor_names,
    factor_matches_from_states,
    gap_fill_factor_states,
    match_checklist_to_factors,
)


@dataclass
class TraversalSeeds:
    factor_matches: list[FactorMatch] = field(default_factory=list)
    chunk_matches: list[ChunkMatch] = field(default_factory=list)

    @property
    def matched_factor_names(self) -> list[str]:
        return affirmed_factor_names(self.factor_matches)

    @property
    def chunk_ids(self) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for m in self.chunk_matches:
            if m.chunk_id not in seen:
                seen.add(m.chunk_id)
                out.append(m.chunk_id)
        return out

    def chunk_ids_in_trace(self, trace: GraphTraversalTrace) -> list[str]:
        ids = list(self.chunk_ids)
        for step in trace.steps:
            if step.chunk_id and step.chunk_id not in ids:
                ids.append(step.chunk_id)
        for node in trace.nodes:
            if node.label == "Chunk":
                cid = str(node.properties.get("chunk_id") or node.name)
                if cid and cid not in ids:
                    ids.append(cid)
        return ids


def _parse_checklist(
    checklist: list[ChecklistItem] | list[ChecklistItemDump],
) -> list[ChecklistItem]:
    parsed: list[ChecklistItem] = []
    for row in checklist:
        if isinstance(row, ChecklistItem):
            parsed.append(row)
        else:
            parsed.append(ChecklistItem.model_validate(row))
    return parsed


def build_traversal_seeds(
    checklist: list[ChecklistItem] | list[ChecklistItemDump],
    *,
    chunk_matches: list[ChunkMatch] | None = None,
    source_message: str | None = None,
) -> TraversalSeeds:
    """Offline / smoke path: checklist rematch. Session disposition uses
    :func:`build_disposition_seeds` instead."""
    factor_matches = match_checklist_to_factors(
        _parse_checklist(checklist), source_message=source_message
    )
    return TraversalSeeds(
        factor_matches=factor_matches,
        chunk_matches=list(chunk_matches or []),
    )


def build_disposition_seeds(
    *,
    factor_states: dict[str, str] | None,
    checklist: list[ChecklistItem] | list[ChecklistItemDump] | None = None,
    chunk_matches: list[ChunkMatch] | None = None,
) -> tuple[TraversalSeeds, dict[str, str], list[FactorMatch]]:
    """Session disposition: synth FactorMatch from interview polarities + chunks.

    Optional regex-only leftover rematch (no current-turn ``source_message``, no
    ``llm_semantic``) gap-fills names never written during intake.
    """
    leftover = match_checklist_to_factors(
        _parse_checklist(checklist or []),
        source_message=None,
        skip_llm=True,
    )
    filled = gap_fill_factor_states(factor_states, leftover)
    synth = factor_matches_from_states(filled)
    seeds = TraversalSeeds(
        factor_matches=synth,
        chunk_matches=list(chunk_matches or []),
    )
    return seeds, filled, leftover
