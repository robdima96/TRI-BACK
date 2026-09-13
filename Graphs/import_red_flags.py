#!/usr/bin/env python3
"""Import red-flags CSV into Neo4j."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from config import DEFAULT_CSV, GRAPHS_DIR
from graph_builder import SCHEMA_STATEMENTS, iter_import_statements, load_chunks
from neo4j_client import Neo4jConfig


def apply_schema(session) -> None:
    for statement in SCHEMA_STATEMENTS:
        session.run(statement)


def clear_graph(session) -> None:
    session.run("MATCH (n) DETACH DELETE n")


def import_csv(csv_path: Path, config: Neo4jConfig, *, wipe: bool = False) -> dict[str, int]:
    rows = load_chunks(csv_path)
    driver = config.driver()

    imported = 0
    with driver.session(database=config.database) as session:
        apply_schema(session)
        if wipe:
            clear_graph(session)

        for cypher, params in iter_import_statements(rows):
            session.run(cypher, params)
            imported += 1

        stats = session.run(
            """
            RETURN
              count { (f:Factor) } AS factors,
              count { (c:Condition) } AS conditions,
              count { (ch:Chunk) } AS chunks,
              count { ()-[r]->() } AS relationships
            """
        ).single()

    driver.close()
    return {
        "rows_imported": imported,
        "factors": stats["factors"],
        "conditions": stats["conditions"],
        "chunks": stats["chunks"],
        "relationships": stats["relationships"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Import red-flags CSV into Neo4j")
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--wipe", action="store_true", help="Delete all nodes before import")
    parser.add_argument("--test", action="store_true", help="Test connection only")
    parser.add_argument("--uri", help="Neo4j URI (overrides .env)")
    parser.add_argument("--username", help="Neo4j username (overrides .env)")
    parser.add_argument("--password", help="Neo4j password (overrides .env)")
    parser.add_argument("--database", help="Neo4j database (overrides .env)")
    args = parser.parse_args(argv)

    config = Neo4jConfig.from_values(
        uri=args.uri,
        username=args.username,
        password=args.password,
        database=args.database,
    )

    if args.test:
        try:
            result = config.test()
        except Exception as exc:
            print(f"Connection failed: {exc}", file=sys.stderr)
            print("Run: python setup_connection.py", file=sys.stderr)
            return 1
        print("Connection OK")
        for key, value in result.items():
            print(f"  {key}: {value}")
        return 0

    if not args.csv.is_file():
        print(f"CSV not found: {args.csv}", file=sys.stderr)
        return 1

    try:
        config.validate()
    except RuntimeError as exc:
        print(exc, file=sys.stderr)
        print("Or load manually: python export_cypher.py", file=sys.stderr)
        return 1

    print(f"Importing {args.csv} -> {config.uri} ({config.database})")
    try:
        result = import_csv(args.csv, config, wipe=args.wipe)
    except Exception as exc:
        print(f"Import failed: {exc}", file=sys.stderr)
        print(
            "\nIf the Python driver cannot reach Aura, use the manual path instead:\n"
            "  python export_cypher.py --wipe\n"
            "  then paste output/red_flags_import.cypher into Neo4j Browser",
            file=sys.stderr,
        )
        return 1

    print("Import complete:")
    for key, value in result.items():
        print(f"  {key}: {value}")
    print(f"\nOpen Neo4j Browser and run queries from {GRAPHS_DIR / 'queries.cypher'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
