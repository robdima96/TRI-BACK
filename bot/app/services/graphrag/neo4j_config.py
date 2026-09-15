"""Neo4j connection settings for the red-flags knowledge graph."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

_REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_GRAPHS_ENV = _REPO_ROOT / "Graphs" / ".env"
_BOT_ENV = _REPO_ROOT / "bot" / ".env"

_KB_MANUAL = (
    _REPO_ROOT / "bot" / "Knowledge Base" / "Red Flags" / "chunks" / "manual"
)
_DEFAULT_CSV = _KB_MANUAL / "red_flags_edges_v4_2026.9.10.csv"
_DEFAULT_INVENTORY = _KB_MANUAL / "red_flags_inventory_v4_2026.9.10.json"
_DEFAULT_FACTORS = _KB_MANUAL / "red_flags_factors_v4_2026.9.10.csv"


def _resolve_env_path(var_name: str, fallback: Path) -> Path:
    """Resolve ``TRI_BACK_GRAPH_*`` (or legacy ``DIGIMSK_GRAPH_*``) from ``bot/.env``."""
    from app.config import env_lookup

    # bot/.env is authoritative for TRI-BACK graph pointers; do not override
    # already-exported process env (tests / CLI overrides).
    if _BOT_ENV.is_file():
        load_dotenv(_BOT_ENV, override=False)
    raw = (env_lookup(var_name) or "").strip()
    if not raw:
        return fallback
    path = Path(raw)
    if not path.is_absolute():
        path = (_REPO_ROOT / path).resolve()
    else:
        path = path.resolve()
    return path


DEFAULT_INVENTORY_PATH = _resolve_env_path("TRI_BACK_GRAPH_INVENTORY", _DEFAULT_INVENTORY)
DEFAULT_CSV_PATH = _resolve_env_path("TRI_BACK_GRAPH_CSV", _DEFAULT_CSV)
DEFAULT_FACTORS_PATH = _resolve_env_path("TRI_BACK_GRAPH_FACTORS", _DEFAULT_FACTORS)


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
