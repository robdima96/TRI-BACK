"""Query helpers for LLM-driven graph navigation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from neo4j import Record

from neo4j_client import Neo4jConfig


@dataclass
class GraphHit:
    factor: str
    condition: str
    relationship: str
    path_type: str
    chunk_id: str
    chunk_string: str
    is_specific: bool
    via_mediation: bool
    mediator: str | None = None


class RedFlagsGraph:
    """Thin Neo4j client for triage-oriented graph traversal."""

    def __init__(self, config: Neo4jConfig | None = None) -> None:
        self._config = config or Neo4jConfig.from_env()
        self._config.validate()
        self._driver = self._config.driver()

    def close(self) -> None:
        self._driver.close()

    def __enter__(self) -> RedFlagsGraph:
        return self

    def __exit__(self, *_) -> None:
        self.close()

    def _run(self, cypher: str, **params: Any) -> list[Record]:
        with self._driver.session(database=self._config.database) as session:
            return list(session.run(cypher, params))

    def list_conditions(self) -> list[str]:
        rows = self._run("MATCH (c:Condition) RETURN c.name AS name ORDER BY name")
        return [row["name"] for row in rows]

    def list_factors(self) -> list[str]:
        rows = self._run("MATCH (f:Factor) RETURN f.name AS name ORDER BY name")
        return [row["name"] for row in rows]

    def conditions_for_factors(self, factors: list[str]) -> list[GraphHit]:
        """Map patient symptoms/traits to candidate red-flag conditions."""
        cypher = """
        UNWIND $factors AS factor_name
        MATCH (f:Factor)
        WHERE toLower(f.name) = toLower(factor_name)
        OPTIONAL MATCH (f)-[r]->(c:Condition)
        OPTIONAL MATCH (f)-[r2]->(mid:Factor)-[:CONTRIBUTES_TO]->(c2:Condition)
        WITH f, r, c, r2, mid, c2
        WITH f,
             CASE WHEN c IS NOT NULL THEN c ELSE c2 END AS condition,
             CASE WHEN c IS NOT NULL THEN r ELSE r2 END AS rel,
             CASE WHEN mid IS NOT NULL THEN mid.name ELSE null END AS mediator
        WHERE condition IS NOT NULL
        MATCH (ch:Chunk)-[:DESCRIBES]->(f)
        MATCH (ch)-[:APPLIES_TO]->(condition)
        RETURN DISTINCT
          f.name AS factor,
          condition.name AS condition,
          type(rel) AS relationship,
          coalesce(rel.path_type, ch.path_type, '') AS path_type,
          coalesce(rel.via_mediation, false) AS via_mediation,
          mediator,
          ch.chunk_id AS chunk_id,
          ch.chunk_string AS chunk_string,
          coalesce(ch.is_specific, false) AS is_specific
        ORDER BY condition, factor
        """
        return [_record_to_hit(row) for row in self._run(cypher, factors=factors)]

    def discriminators_for_conditions(self, conditions: list[str]) -> list[GraphHit]:
        """Pull is_specific chunks when multiple conditions are in play."""
        cypher = """
        UNWIND $conditions AS condition_name
        MATCH (c:Condition)
        WHERE toLower(c.name) = toLower(condition_name)
        MATCH (ch:Chunk {is_specific: true})-[:APPLIES_TO]->(c)
        MATCH (ch)-[:DESCRIBES]->(f:Factor)
        RETURN
          f.name AS factor,
          c.name AS condition,
          ch.edges AS relationship,
          ch.path_type AS path_type,
          false AS via_mediation,
          null AS mediator,
          ch.chunk_id AS chunk_id,
          ch.chunk_string AS chunk_string,
          true AS is_specific
        ORDER BY condition, factor
        """
        return [_record_to_hit(row) for row in self._run(cypher, conditions=conditions)]

    def neighborhood(self, name: str, hops: int = 2) -> list[dict[str, Any]]:
        """Return nodes and edges around a factor or condition (for visualization)."""
        cypher = """
        MATCH (start)
        WHERE (start:Factor OR start:Condition) AND toLower(start.name) = toLower($name)
        CALL {
            WITH start
            MATCH p = (start)-[*1..$hops]-(n)
            WHERE n:Factor OR n:Condition OR n:Chunk
            RETURN p
            LIMIT 80
        }
        RETURN p
        """
        paths = self._run(cypher, name=name, hops=hops)
        return [{"path": row["p"]} for row in paths]

    def evidence_for_link(self, factor: str, condition: str) -> list[dict[str, str]]:
        cypher = """
        MATCH (f:Factor)
        WHERE toLower(f.name) = toLower($factor)
        MATCH (c:Condition)
        WHERE toLower(c.name) = toLower($condition)
        MATCH (ch:Chunk)-[:DESCRIBES]->(f)
        MATCH (ch)-[:APPLIES_TO]->(c)
        RETURN ch.chunk_id AS chunk_id,
               ch.chunk_string AS chunk_string,
               ch.evidence AS evidence,
               ch.evidence_level AS evidence_level
        ORDER BY ch.chunk_id
        """
        return [dict(row) for row in self._run(cypher, factor=factor, condition=condition)]

    def summary(self) -> dict[str, int]:
        row = self._run(
            """
            RETURN
              count { (f:Factor) } AS factors,
              count { (c:Condition) } AS conditions,
              count { (ch:Chunk) } AS chunks,
              count { ()-[r]->() } AS relationships
            """
        )[0]
        return dict(row)


def _record_to_hit(row: Record) -> GraphHit:
    return GraphHit(
        factor=row["factor"],
        condition=row["condition"],
        relationship=row["relationship"] or "",
        path_type=row["path_type"] or "",
        chunk_id=row["chunk_id"] or "",
        chunk_string=row["chunk_string"] or "",
        is_specific=bool(row["is_specific"]),
        via_mediation=bool(row["via_mediation"]),
        mediator=row["mediator"],
    )


if __name__ == "__main__":
    with RedFlagsGraph() as graph:
        print("Graph summary:", graph.summary())
        print("Conditions:", ", ".join(graph.list_conditions()))
        hits = graph.conditions_for_factors(["Fever", "Recent trauma"])
        print(f"\nSample traversal ({len(hits)} hits):")
        for hit in hits[:5]:
            print(f"  {hit.factor} -[{hit.relationship}]-> {hit.condition} ({hit.chunk_id})")
