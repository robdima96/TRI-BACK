"""Grounded clinical ontology derived from the red-flags ground-truth CSV.

Defines what exists in the graph

The *narrative* clinical reasoning (how factor clusters raise suspicion) lives in
the hand-editable prompt at ``prompts/clinical_reasoning_framework.md``. This
module instead builds the *structural* half - the concrete conditions, factors,
mediators (conceptual gateways), and relation vocabulary that actually exist in
``red_flags_manual_failsafe.csv``. Rendering the ontology card straight from the
ground truth keeps the agent's vocabulary in sync with the graph and stops it
from reasoning over conditions or factors that are not real.

This is the TRI-BACK analogue of the ``<MainConcepts> / <MainTopics> /
<ConceptualGateways> / <Relations>`` block in
``Graphs/n8n-infranodus-templates/reasoning-expert-graph-ontology.json``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from app.services.graphrag.csv_rows import (
    ChunkRow,
    FactorRow,
    load_chunks,
    load_factor_sheet,
    load_inventory_factors,
)
from app.services.graphrag.neo4j_config import (
    DEFAULT_CSV_PATH,
    DEFAULT_FACTORS_PATH,
    DEFAULT_INVENTORY_PATH,
)


@dataclass(frozen=True)
class FactorQuestionSpec:
    """Node properties for one Factor from the v4+ factors CSV."""

    factor: str
    askable: bool
    intent: str
    fallback: str
    synonyms: tuple[str, ...]

    @classmethod
    def from_row(cls, row: FactorRow) -> FactorQuestionSpec:
        return cls(
            factor=row.source_nodes,
            askable=row.askable,
            intent=row.intent,
            fallback=row.fallback,
            synonyms=row.synonyms,
        )


@dataclass(frozen=True)
class RedFlagOntology:
    """Structural summary of the red-flags graph (conditions, factors, gateways)."""

    graph_version: str
    conditions: tuple[str, ...]
    factors_by_condition: dict[str, tuple[str, ...]]
    mediators: tuple[str, ...]
    relations: tuple[str, ...]
    all_factors: tuple[str, ...] = field(default_factory=tuple)
    is_specific_by_factor: dict[str, bool] = field(default_factory=dict)
    factor_specs: dict[str, FactorQuestionSpec] = field(default_factory=dict)

    def condition_set(self) -> set[str]:
        return set(self.conditions)

    def factor_set(self) -> set[str]:
        return set(self.all_factors)

    def factor_is_specific(self, factor: str) -> bool:
        spec = self._spec_for(factor)
        key = spec.factor if spec else factor
        return bool(self.is_specific_by_factor.get(key, False))

    def _spec_for(self, factor: str) -> FactorQuestionSpec | None:
        if factor in self.factor_specs:
            return self.factor_specs[factor]
        want = factor.casefold().strip()
        for name, spec in self.factor_specs.items():
            if name.casefold() == want:
                return spec
        return None

    def get_factor_question_spec(self, factor: str) -> FactorQuestionSpec | None:
        return self._spec_for(factor)


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
def _load_ontology(
    csv_path: str,
    factors_path: str,
    inventory_path: str,
    graph_version: str,
) -> RedFlagOntology:
    rows: list[ChunkRow] = load_chunks(Path(csv_path))
    inventory = load_inventory_factors(Path(inventory_path))
    factor_rows = load_factor_sheet(Path(factors_path), inventory)

    conditions: list[str] = []
    factors_by_condition: dict[str, list[str]] = {}
    mediators: list[str] = []
    relations: list[str] = []
    all_factors: list[str] = []
    is_specific_by_factor: dict[str, bool] = {}

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
            if row.is_specific:
                is_specific_by_factor[factor] = True
            else:
                is_specific_by_factor.setdefault(factor, False)
        if row.edges.strip():
            relations.append(row.edges.strip().upper().replace(" ", "_"))
        # Mediators are the "path" nodes on mediated / both rows: the conceptual
        # gateways through which background risk factors reach a condition.
        if row.path_type in {"mediated", "both"} and row.path and row.path != "-":
            mediators.append(row.path.strip())

    specs = {fr.source_nodes: FactorQuestionSpec.from_row(fr) for fr in factor_rows}

    return RedFlagOntology(
        graph_version=graph_version,
        conditions=_dedupe_preserve(conditions),
        factors_by_condition={
            cond: _dedupe_preserve(facs) for cond, facs in factors_by_condition.items()
        },
        mediators=_dedupe_preserve(mediators),
        relations=_dedupe_preserve(relations),
        all_factors=_dedupe_preserve(all_factors),
        is_specific_by_factor=is_specific_by_factor,
        factor_specs=specs,
    )


def load_ontology(
    csv_path: Path | None = None,
    graph_version: str = "red_flags/v1",
    *,
    factors_path: Path | None = None,
    inventory_path: Path | None = None,
) -> RedFlagOntology:
    """Load (and cache) the structural ontology from the ground-truth CSVs."""
    edges = csv_path or DEFAULT_CSV_PATH
    factors = factors_path or DEFAULT_FACTORS_PATH
    inventory = inventory_path or DEFAULT_INVENTORY_PATH
    return _load_ontology(
        str(edges.resolve()),
        str(factors.resolve()),
        str(inventory.resolve()),
        graph_version,
    )


def get_factor_question_spec(
    factor: str,
    ontology: RedFlagOntology | None = None,
) -> FactorQuestionSpec | None:
    """Return askable/intent/fallback/synonyms for ``factor``, or None if unknown."""
    ont = ontology or load_ontology()
    return ont.get_factor_question_spec(factor)


def factor_is_specific(factor: str, ontology: RedFlagOntology | None = None) -> bool:
    ont = ontology or load_ontology()
    return ont.factor_is_specific(factor)


def is_legal_factor_ask(factor: str, ontology: RedFlagOntology | None = None) -> bool:
    spec = get_factor_question_spec(factor, ontology)
    return bool(spec and spec.askable)


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
