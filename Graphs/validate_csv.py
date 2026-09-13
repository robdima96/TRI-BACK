#!/usr/bin/env python3
"""Validate CSV parsing and print graph stats without connecting to Neo4j."""

from __future__ import annotations

from collections import Counter

from config import DEFAULT_CSV
from graph_builder import iter_import_statements, load_chunks, sanitize_rel_type


def main() -> int:
    rows = load_chunks(DEFAULT_CSV)
    rel_types = Counter(sanitize_rel_type(r.edges) for r in rows)
    path_types = Counter(r.path_type for r in rows)
    conditions = Counter(r.parent_id for r in rows)
    sources = {r.source_nodes for r in rows}
    mediators = {r.path for r in rows if r.path and r.path != "-"}
    factors = sources | mediators
    mediators_only = mediators - sources
    mediators_also_sources = mediators & sources

    mediated_rows = [
        r for r in rows if r.path and r.path != "-" and r.path_type in {"mediated", "both"}
    ]

    statements = list(iter_import_statements(rows))
    print(f"CSV: {DEFAULT_CSV}")
    print(f"  rows: {len(rows)}")
    print(f"  unique Factor names (source_nodes + path): {len(factors)}")
    print(f"  path mediators: {len(mediators)}")
    print(f"    also appear as source_nodes: {sorted(mediators_also_sources)}")
    print(f"    mediator-only (not a source_nodes value): {sorted(mediators_only)}")
    print(f"  mediated/both rows creating Factor chains: {len(mediated_rows)}")
    print(f"  conditions: {dict(conditions)}")
    print(f"  relationship types: {dict(rel_types)}")
    print(f"  path types: {dict(path_types)}")
    print(f"  cypher statements generated: {len(statements)}")
    print("\nSample mediated chains (source -> path -> condition):")
    for row in mediated_rows[:5]:
        print(f"  {row.source_nodes} -[{row.edges}]-> {row.path} -[CONTRIBUTES_TO]-> {row.parent_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
