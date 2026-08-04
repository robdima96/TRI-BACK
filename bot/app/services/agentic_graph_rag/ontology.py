"""Grounded clinical ontology derived from the red-flags ground-truth CSV.

Defines what exists in the graph

The *narrative* clinical reasoning (how factor clusters raise suspicion) lives in
the hand-editable prompt at ``prompts/clinical_reasoning_framework.md``. This
module instead builds the *structural* half - the concrete conditions, factors,
mediators (conceptual gateways), and relation vocabulary that actually exist in
``red_flags_manual_failsafe.csv``. Rendering the ontology card straight from the
ground truth keeps the agent's vocabulary in sync with the graph and stops it
from reasoning over conditions or factors that are not real.

This is the DigiMSK analogue of the ``<MainConcepts> / <MainTopics> /
<ConceptualGateways> / <Relations>`` block in
``Graphs/n8n-infranodus-templates/reasoning-expert-graph-ontology.json``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from app.services.graphrag.csv_rows import ChunkRow, load_chunks
from app.services.graphrag.neo4j_config import DEFAULT_CSV_PATH


@dataclass(frozen=True)
class RedFlagOntology:
    """Structural summary of the red-flags graph (conditions, factors, gateways)."""

    graph_version: str
    conditions: tuple[str, ...]
    factors_by_condition: dict[str, tuple[str, ...]]
    mediators: tuple[str, ...]
    relations: tuple[str, ...]
    all_factors: tuple[str, ...] = field(default_factory=tuple)

    def condition_set(self) -> set[str]:
        return set(self.conditions)

    def factor_set(self) -> set[str]:
        return set(self.all_factors)


def tally_touched_conditions(
    matched_factors: list[str] | tuple[str, ...],
    ontology: RedFlagOntology,
) -> list[dict[str, object]]:
    """Count condition membership hits without traversing or scoring graph paths.

    The result is an orientation aid for the agent, not a probability or
    deterministic risk ranking. Ordering is stable: most factor hits first,
    then ontology order for ties.
    """
    matched = set(matched_factors)
    touched: list[dict[str, object]] = []
    for condition in ontology.conditions:
        factors = [
            factor
            for factor in ontology.factors_by_condition.get(condition, ())
            if factor in matched
        ]
        if factors:
            touched.append(
                {
                    "condition": condition,
                    "factor_hit_count": len(factors),
                    "matched_factors": factors,
                }
            )
    ontology_order = {name: i for i, name in enumerate(ontology.conditions)}
    touched.sort(
        key=lambda row: (
            -int(row["factor_hit_count"]),
            ontology_order.get(str(row["condition"]), len(ontology_order)),
        )
    )
    return touched


def _dedupe_preserve(values: list[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    out: list[str] = []
    for v in values:
        key = v.casefold().strip()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(v.strip())
    return tuple(out)


@lru_cache(maxsize=4)
def _load_ontology(csv_path: str, graph_version: str) -> RedFlagOntology:
    rows: list[ChunkRow] = load_chunks(Path(csv_path))

    conditions: list[str] = []
    factors_by_condition: dict[str, list[str]] = {}
    mediators: list[str] = []
    relations: list[str] = []
    all_factors: list[str] = []

    for row in rows:
        condition = row.parent_id.strip()
        factor = row.source_nodes.strip()
        if condition:
            conditions.append(condition)
            factors_by_condition.setdefault(condition, [])
            if factor:
                factors_by_condition[condition].append(factor)
        if factor:
            all_factors.append(factor)
        if row.edges.strip():
            relations.append(row.edges.strip().upper().replace(" ", "_"))
        # Mediators are the "path" nodes on mediated / both rows: the conceptual
        # gateways through which background risk factors reach a condition.
        if row.path_type in {"mediated", "both"} and row.path and row.path != "-":
            mediators.append(row.path.strip())

    return RedFlagOntology(
        graph_version=graph_version,
        conditions=_dedupe_preserve(conditions),
        factors_by_condition={
            cond: _dedupe_preserve(facs) for cond, facs in factors_by_condition.items()
        },
        mediators=_dedupe_preserve(mediators),
        relations=_dedupe_preserve(relations),
        all_factors=_dedupe_preserve(all_factors),
    )


def load_ontology(
    csv_path: Path | None = None, graph_version: str = "red_flags/v1"
) -> RedFlagOntology:
    """Load (and cache) the structural ontology from the ground-truth CSV."""
    path = csv_path or DEFAULT_CSV_PATH
    return _load_ontology(str(path.resolve()), graph_version)


def render_ontology_card(ontology: RedFlagOntology | None = None) -> str:
    """Render a compact, grounded ontology card for the reasoning prompt."""
    ont = ontology or load_ontology()
    lines: list[str] = []
    lines.append(f"GRAPH VERSION: {ont.graph_version}")
    lines.append("")
    lines.append(
        "CONDITIONS (only these may be named; "
        "Non-specific Mechanical Cause is the common default when present "
        "and serious red-flag clusters are absent):"
    )
    lines.append("  " + ", ".join(ont.conditions))
    lines.append("")
    lines.append("CONDITION -> CONTRIBUTING FACTORS (ground truth):")
    for cond in ont.conditions:
        facs = ont.factors_by_condition.get(cond, ())
        if facs:
            lines.append(f"  {cond}: " + ", ".join(facs))
    lines.append("")
    if ont.mediators:
        lines.append(
            "CONCEPTUAL GATEWAYS (mediators linking background risk "
            "or loading patterns to a condition):"
        )
        lines.append("  " + ", ".join(ont.mediators))
        lines.append("")
    lines.append("RELATION VOCABULARY (edge types you may cite):")
    lines.append("  " + ", ".join(ont.relations))
    return "\n".join(lines)
