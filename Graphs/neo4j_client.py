"""Neo4j connection helpers — env file, CLI overrides, and connectivity test."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv
from neo4j import GraphDatabase

from config import GRAPHS_DIR

ENV_PATH = GRAPHS_DIR / ".env"


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
        # Aura Free: database name is usually the instance id from the hostname.
        if ".databases.neo4j.io" in uri:
            host = uri.split("://", 1)[-1].split("/")[0].split(":")[0]
            instance_id = host.split(".")[0]
            if instance_id:
                return instance_id
        if username and username != "neo4j":
            return username
        return "neo4j"

    @classmethod
    def from_env(cls) -> Neo4jConfig:
        load_dotenv(ENV_PATH, override=True)
        uri = cls._normalize_uri(os.getenv("NEO4J_URI", ""))
        username = os.getenv("NEO4J_USERNAME", "neo4j").strip()
        explicit_db = os.getenv("NEO4J_DATABASE", "").strip()
        return cls(
            uri=uri,
            username=username,
            password=os.getenv("NEO4J_PASSWORD", "").strip(),
            database=cls._resolve_database(uri, username, explicit_db),
        )

    @classmethod
    def from_values(
        cls,
        *,
        uri: str | None = None,
        username: str | None = None,
        password: str | None = None,
        database: str | None = None,
    ) -> Neo4jConfig:
        base = cls.from_env()
        resolved_uri = cls._normalize_uri(uri if uri is not None else base.uri)
        resolved_username = (username if username is not None else base.username).strip()
        resolved_password = (password if password is not None else base.password).strip()
        if database is not None:
            explicit_db = database.strip()
        else:
            load_dotenv(ENV_PATH, override=True)
            explicit_db = os.getenv("NEO4J_DATABASE", "").strip()
        return cls(
            uri=resolved_uri,
            username=resolved_username,
            password=resolved_password,
            database=cls._resolve_database(resolved_uri, resolved_username, explicit_db),
        )

    def validate(self) -> None:
        missing = [name for name, value in [
            ("NEO4J_URI", self.uri),
            ("NEO4J_PASSWORD", self.password),
        ] if not value]
        if missing:
            raise RuntimeError(
                f"Missing {', '.join(missing)}. Run: python setup_connection.py"
            )
        if "://" not in self.uri:
            raise RuntimeError(
                f"NEO4J_URI must include a scheme (e.g. neo4j+s://bb1ec188.databases.neo4j.io), got: {self.uri!r}"
            )

    def driver(self):
        self.validate()
        return GraphDatabase.driver(self.uri, auth=(self.username, self.password))

    def test(self) -> dict[str, str | int]:
        """Verify credentials and return basic server info."""
        self.validate()
        driver = self.driver()
        try:
            with driver.session(database=self.database) as session:
                record = session.run(
                    "RETURN 1 AS ok, count { (n) } AS node_count"
                ).single()
            return {
                "status": "ok",
                "uri": self.uri,
                "database": self.database,
                "node_count": record["node_count"],
            }
        finally:
            driver.close()

    def write_env(self) -> Path:
        lines = [
            f"NEO4J_URI={self.uri}",
            f"NEO4J_USERNAME={self.username}",
            f"NEO4J_PASSWORD={self.password}",
            f"NEO4J_DATABASE={self.database}",
            "RED_FLAGS_CSV=bot/Knowledge Base/Red Flags/chunks/manual/red_flags_manual_failsafe.csv",
            "",
        ]
        ENV_PATH.write_text("\n".join(lines), encoding="utf-8")
        return ENV_PATH
