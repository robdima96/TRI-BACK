#!/usr/bin/env python3
"""Configure and test your Neo4j Aura / Desktop connection."""

from __future__ import annotations

import argparse
import sys

from neo4j_client import ENV_PATH, Neo4jConfig


def _prompt(label: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    value = input(f"{label}{suffix}: ").strip()
    return value or default


def _yes_no(prompt: str, *, default: bool = False) -> bool:
    hint = "Y/n" if default else "y/N"
    value = input(f"{prompt} [{hint}]: ").strip().lower()
    if not value:
        return default
    return value in {"y", "yes"}


def _print_config(config: Neo4jConfig, *, stored: bool = False) -> None:
    prefix = "Loaded from Graphs/.env" if stored else "Connection settings"
    print(prefix)
    print(f"  NEO4J_URI:       {config.uri or '(not set)'}")
    print(f"  NEO4J_USERNAME:  {config.username or '(not set)'}")
    print(f"  NEO4J_PASSWORD:  {config.password or '(not set)'}")
    print(f"  NEO4J_DATABASE:  {config.database}")
    if stored and not config.uri:
        print("  (Graphs/.env is missing URI — choose 'no' and enter credentials manually)")


def load_stored_config() -> Neo4jConfig:
    config = Neo4jConfig.from_env()
    _print_config(config, stored=True)
    return config


def interactive_setup() -> Neo4jConfig:
    print("Neo4j connection setup")
    print("-" * 40)

    if _yes_no(f"Use credentials stored in {ENV_PATH.name}?"):
        return load_stored_config()

    print()
    print("Enter credentials manually. Get URI from:")
    print("  Aura:    https://console.neo4j.io  -> your instance -> Connect")
    print("  Desktop: bolt://localhost:7687")
    print()
    print("NEO4J_DATABASE: use 'neo4j' for Desktop; for Aura it is usually")
    print("  your instance id (same as the id in the URI hostname).")
    print()

    existing = Neo4jConfig.from_env()
    uri = _prompt(
        "NEO4J_URI (full URI or Aura instance id, e.g. bb1ec188)",
        existing.uri,
    )
    uri = Neo4jConfig._normalize_uri(uri)
    username = _prompt("NEO4J_USERNAME", existing.username or "neo4j")
    password = _prompt(
        "NEO4J_PASSWORD",
        existing.password,
    )
    database = _prompt(
        "NEO4J_DATABASE (Aura: instance id; Desktop: neo4j)",
        existing.database or Neo4jConfig._resolve_database(uri, username, ""),
    )

    config = Neo4jConfig(uri=uri, username=username, password=password, database=database)
    print()
    _print_config(config)
    return config


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Configure Graphs/.env and test Neo4j connectivity"
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Test the current .env connection only (no prompts)",
    )
    parser.add_argument("--uri", help="Override NEO4J_URI")
    parser.add_argument("--username", help="Override NEO4J_USERNAME")
    parser.add_argument("--password", help="Override NEO4J_PASSWORD")
    parser.add_argument("--database", help="Override NEO4J_DATABASE")
    parser.add_argument(
        "--write",
        action="store_true",
        help="With --uri/--username/--password, write .env without prompts",
    )
    args = parser.parse_args(argv)

    if args.test:
        config = Neo4jConfig.from_values(
            uri=args.uri,
            username=args.username,
            password=args.password,
            database=args.database,
        )
        _print_config(config, stored=True)
    elif args.write and args.uri and args.password:
        config = Neo4jConfig.from_values(
            uri=args.uri,
            username=args.username,
            password=args.password,
            database=args.database,
        )
    else:
        config = interactive_setup()

    try:
        result = config.test()
    except Exception as exc:
        print(f"Connection failed: {exc}", file=sys.stderr)
        print(
            "\nTips:\n"
            "  - Aura URI must look like neo4j+s://<id>.databases.neo4j.io\n"
            "  - Instance must be Running in the Aura console\n"
            "  - NEO4J_DATABASE for Aura is usually your instance id (e.g. bb1ec188)\n"
            "  - Or export Cypher and load via Browser: python export_cypher.py",
            file=sys.stderr,
        )
        return 1

    if not args.test:
        path = config.write_env()
        print(f"\nSaved credentials to {path}")

    print("Connection OK")
    print(f"  uri:      {result['uri']}")
    print(f"  database: {result['database']}")
    print(f"  nodes:    {result['node_count']}")
    print("\nNext: python import_red_flags.py --wipe")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
