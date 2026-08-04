"""Neo4j connection settings for the red-flags knowledge graph."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

_REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_GRAPHS_ENV = _REPO_ROOT / "Graphs" / ".env"
_BOT_ENV = _REPO_ROOT / "bot" / ".env"

_V1_INVENTORY = (
    _REPO_ROOT / "Graphs" / "backups" / "red flags" / "v1" / "inventory.json"
)
_V1_CSV = (
    _REPO_ROOT
    / "Graphs"
    / "backups"
    / "red flags"
    / "v1"
    / "source"
    / "red_flags_manual_failsafe.csv"
)


def _resolve_env_path(var_name: str, fallback: Path) -> Path:
    """Resolve ``DIGIMSK_GRAPH_*`` paths from ``bot/.env`` (or process env)."""
    # bot/.env is authoritative for DigiMSK graph pointers; do not override
    # already-exported process env (tests / CLI overrides).
    if _BOT_ENV.is_file():
        load_dotenv(_BOT_ENV, override=False)
    raw = (os.getenv(var_name) or "").strip()
    if not raw:
        return fallback
    path = Path(raw)
    if not path.is_absolute():
        path = (_REPO_ROOT / path).resolve()
    else:
        path = path.resolve()
    return path


DEFAULT_INVENTORY_PATH = _resolve_env_path("DIGIMSK_GRAPH_INVENTORY", _V1_INVENTORY)
DEFAULT_CSV_PATH = _resolve_env_path("DIGIMSK_GRAPH_CSV", _V1_CSV)


@dataclass(frozen=True)
class Neo4jConfig:
    uri: str
    username: str
    password: str
    database: str = "neo4j"

    @classmethod
    def _normalize_uri(cls, uri: str) -> str:
        uri = uri.strip()
        if not uri:
            return uri
        if "://" not in uri:
            instance_id = uri.split("/")[0].split(":")[0]
            return f"neo4j+s://{instance_id}.databases.neo4j.io"
        return uri

    @classmethod
    def _resolve_database(cls, uri: str, username: str, explicit: str) -> str:
        if explicit:
            return explicit
        if ".databases.neo4j.io" in uri:
            host = uri.split("://", 1)[-1].split("/")[0].split(":")[0]
            instance_id = host.split(".")[0]
            if instance_id:
                return instance_id
        if username and username != "neo4j":
            return username
        return "neo4j"

    @classmethod
    def from_env(cls, env_path: Path | None = None) -> Neo4jConfig:
        load_dotenv(env_path or DEFAULT_GRAPHS_ENV, override=True)
        uri = cls._normalize_uri(os.getenv("NEO4J_URI", ""))
        username = os.getenv("NEO4J_USERNAME", "neo4j").strip()
        explicit_db = os.getenv("NEO4J_DATABASE", "").strip()
        return cls(
            uri=uri,
            username=username,
            password=os.getenv("NEO4J_PASSWORD", "").strip(),
            database=cls._resolve_database(uri, username, explicit_db),
        )

    def validate(self) -> None:
        missing = [
            name
            for name, value in [
                ("NEO4J_URI", self.uri),
                ("NEO4J_PASSWORD", self.password),
            ]
            if not value
        ]
        if missing:
            raise RuntimeError(
                f"Missing {', '.join(missing)}. Configure Graphs/.env or set env vars."
            )
        if "://" not in self.uri:
            raise RuntimeError(
                "NEO4J_URI must include a scheme "
                f"(e.g. neo4j+s://<instance>.databases.neo4j.io), got: {self.uri!r}"
            )

    def driver(self):
        from neo4j import GraphDatabase

        self.validate()
        return GraphDatabase.driver(self.uri, auth=(self.username, self.password))
