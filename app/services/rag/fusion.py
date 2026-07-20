"""Merge factor matching and chunk seeds for graph traversal."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.schemas import ChecklistItem, ChunkMatch
from app.services.graphrag.schemas import FactorMatch, GraphTraversalTrace
from app.services.rag.factor_matcher import match_checklist_to_factors


@dataclass
class TraversalSeeds:
    factor_matches: list[FactorMatch] = field(default_factory=list)
    chunk_matches: list[ChunkMatch] = field(default_factory=list)

    @property
    def matched_factor_names(self) -> list[str]:
        return [m.factor_name for m in self.factor_matches if m.factor_name]

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


def build_traversal_seeds(
    checklist: list[ChecklistItem] | list[dict[str, str]],
    *,
    chunk_matches: list[ChunkMatch] | None = None,
) -> TraversalSeeds:
    """Graph path: factor matches + optional RAG chunk seeds (from retrieve_evidence_node)."""
    parsed: list[ChecklistItem] = []
    for row in checklist:
        if isinstance(row, ChecklistItem):
            parsed.append(row)
        else:
            parsed.append(ChecklistItem.model_validate(row))

    factor_matches = match_checklist_to_factors(parsed)
    return TraversalSeeds(
        factor_matches=factor_matches,
        chunk_matches=list(chunk_matches or []),
    )
