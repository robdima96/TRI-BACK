#!/usr/bin/env python3
"""Export red-flags graph as a .cypher file for manual Neo4j Browser import."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from config import DEFAULT_CSV, GRAPHS_DIR
from cypher_export import render_literal_cypher
from graph_builder import SCHEMA_STATEMENTS, iter_import_statements, load_chunks

OUTPUT_DIR = GRAPHS_DIR / "output"
DEFAULT_OUTPUT = OUTPUT_DIR / "red_flags_import.cypher"


def build_cypher_file(csv_path: Path, *, wipe: bool = False) -> str:
    rows = load_chunks(csv_path)
    blocks: list[str] = [
        "// TRI-BACK Red Flags — generated import script",
        "// Open Neo4j Browser (Aura or Desktop), paste sections or run the full file.",
        f"// Source: {csv_path}",
        f"// Rows: {len(rows)}",
        "",
    ]

    if wipe:
        blocks.extend([
            "// --- wipe existing graph ---",
            "MATCH (n) DETACH DELETE n;",
            "",
        ])

    blocks.append("// --- schema ---")
    blocks.extend(f"{stmt};" for stmt in SCHEMA_STATEMENTS)
    blocks.append("")

    blocks.append("// --- data ---")
    for index, (cypher, params) in enumerate(iter_import_statements(rows), start=1):
        chunk_id = params["chunk_id"]
        blocks.append(f"// row {index}: {chunk_id}")
        blocks.append(render_literal_cypher(cypher, params) + ";")
        blocks.append("")

    blocks.append("// --- verify ---")
    blocks.append(
        "RETURN\n"
        "  count { (f:Factor) } AS factors,\n"
        "  count { (c:Condition) } AS conditions,\n"
        "  count { (ch:Chunk) } AS chunks,\n"
        "  count { ()-[r]->() } AS relationships;"
    )

    return "\n".join(blocks)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Export CSV graph to a Cypher file (no live DB connection required)"
    )
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--wipe", action="store_true", help="Prepend MATCH (n) DETACH DELETE n")
    args = parser.parse_args(argv)

    if not args.csv.is_file():
        print(f"CSV not found: {args.csv}", file=sys.stderr)
        return 1

    content = build_cypher_file(args.csv, wipe=args.wipe)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(content, encoding="utf-8")

    print(f"Wrote {args.output}")
    print("Manual import:")
    print("  1. Open Neo4j Browser for your Aura / Desktop instance")
    print("  2. Open the file and paste into the query editor")
    print("  3. Run (or run section-by-section if your Browser has size limits)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
