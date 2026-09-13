"""Neo4j connection and path configuration."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

GRAPHS_DIR = Path(__file__).resolve().parent
REPO_ROOT = GRAPHS_DIR.parent

load_dotenv(GRAPHS_DIR / ".env", override=True)


def _require(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(
            f"Missing {name}. Copy Graphs/.env.example to Graphs/.env and set credentials."
        )
    return value


NEO4J_URI = os.getenv("NEO4J_URI", "")
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")

DEFAULT_CSV = REPO_ROOT / os.getenv(
    "RED_FLAGS_CSV",
    "bot/Knowledge Base/Red Flags/chunks/manual/red_flags_manual_failsafe.csv",
)
