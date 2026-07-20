"""Neo4j client for auditable Factor→Condition graph traversal (legacy / Graphs tooling)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from neo4j import Record

from app.services.graphrag.elements import edge_from_record, merge_elements, node_from_record
from app.services.graphrag.graph_client_protocol import PathSegment
from app.services.graphrag.neo4j_config import Neo4jConfig
from app.services.graphrag.schemas import GraphEdge, GraphNode


@dataclass
class Neo4jGraphClient:
    config: Neo4jConfig
    _driver: Any = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if self._driver is None:
            self._driver = self.config.driver()

    def close(self) -> None:
        if self._driver is not None:
            self._driver.close()
            self._driver = None

    def __enter__(self) -> Neo4jGraphClient:
        return self

    def __exit__(self, *_) -> None:
        self.close()

    def _run(self, cypher: str, **params: Any) -> list[Record]:
        with self._driver.session(database=self.config.database) as session:
            return list(session.run(cypher, params))

    def paths_for_factors(self, factors: list[str]) -> list[PathSegment]:
        if not factors:
            return []
        cypher = """
        UNWIND $factors AS factor_name
        MATCH (f:Factor)
        WHERE toLower(f.name) = toLower(factor_name)

        OPTIONAL MATCH (f)-[r]->(c:Condition)
        WHERE r IS NOT NULL AND NOT type(r) = 'CONTRIBUTES_TO'
        OPTIONAL MATCH (ch:Chunk)-[d:DESCRIBES]->(f)
        OPTIONAL MATCH (ch)-[a:APPLIES_TO]->(c)
        WITH f, r, c, ch, d, a,
             false AS via_mediation,
             null AS mid,
             null AS r_contrib
        WHERE c IS NOT NULL

        RETURN
          f.name AS factor,
          elementId(f) AS factor_element_id,
          c.name AS condition,
          elementId(c) AS condition_element_id,
          type(r) AS relationship,
          elementId(r) AS relationship_element_id,
          coalesce(r.path_type, ch.path_type, '') AS path_type,
          via_mediation,
          null AS mediator,
          null AS mediator_element_id,
          null AS contributes_element_id,
          coalesce(ch.chunk_id, '') AS chunk_id,
          coalesce(ch.chunk_string, '') AS chunk_string,
          elementId(ch) AS chunk_element_id,
          elementId(d) AS describes_element_id,
          elementId(a) AS applies_element_id,
          coalesce(ch.is_specific, false) AS is_specific

        UNION

        UNWIND $factors AS factor_name
        MATCH (f:Factor)
        WHERE toLower(f.name) = toLower(factor_name)
        MATCH (f)-[r1]->(mid:Factor)-[r2:CONTRIBUTES_TO]->(c:Condition)
        OPTIONAL MATCH (ch:Chunk)-[d:DESCRIBES]->(f)
        OPTIONAL MATCH (ch)-[a:APPLIES_TO]->(c)

        RETURN
          f.name AS factor,
          elementId(f) AS factor_element_id,
          c.name AS condition,
          elementId(c) AS condition_element_id,
          type(r1) AS relationship,
          elementId(r1) AS relationship_element_id,
          coalesce(r1.path_type, r2.path_type, ch.path_type, 'mediated') AS path_type,
          true AS via_mediation,
          mid.name AS mediator,
          elementId(mid) AS mediator_element_id,
          elementId(r2) AS contributes_element_id,
          coalesce(ch.chunk_id, r1.chunk_id, r2.chunk_id, '') AS chunk_id,
          coalesce(ch.chunk_string, '') AS chunk_string,
          elementId(ch) AS chunk_element_id,
          elementId(d) AS describes_element_id,
          elementId(a) AS applies_element_id,
          coalesce(ch.is_specific, false) AS is_specific

        ORDER BY condition, factor, chunk_id
        """
        segments: list[PathSegment] = []
        seen: set[tuple[str, str, str, str, str]] = set()
        for row in self._run(cypher, factors=factors):
            key = (
                row["factor"] or "",
                row["condition"] or "",
                row["relationship"] or "",
                row["mediator"] or "",
                row["chunk_id"] or "",
            )
            if key in seen:
                continue
            seen.add(key)
            segments.append(
                PathSegment(
                    factor=row["factor"] or "",
                    factor_element_id=row["factor_element_id"] or "",
                    condition=row["condition"] or "",
                    condition_element_id=row["condition_element_id"] or "",
                    relationship=row["relationship"] or "",
                    relationship_element_id=row["relationship_element_id"] or "",
                    path_type=row["path_type"] or "",
                    via_mediation=bool(row["via_mediation"]),
                    mediator=row["mediator"],
                    mediator_element_id=row["mediator_element_id"],
                    contributes_element_id=row["contributes_element_id"],
                    chunk_id=row["chunk_id"] or "",
                    chunk_string=row["chunk_string"] or "",
                    chunk_element_id=row["chunk_element_id"],
                    describes_element_id=row["describes_element_id"],
                    applies_element_id=row["applies_element_id"],
                    is_specific=bool(row["is_specific"]),
                )
            )
        return segments

    def fetch_nodes_by_element_ids(self, element_ids: list[str]) -> list[GraphNode]:
        if not element_ids:
            return []
        cypher = """
        UNWIND $ids AS eid
        MATCH (n)
        WHERE elementId(n) = eid
          AND (n:Factor OR n:Condition OR n:Chunk)
        RETURN elementId(n) AS element_id, labels(n) AS labels, properties(n) AS props
        """
        nodes: list[GraphNode] = []
        for row in self._run(cypher, ids=element_ids):
            nodes.append(
                node_from_record(
                    element_id=row["element_id"],
                    labels=list(row["labels"]),
                    properties=dict(row["props"]),
                )
            )
        return nodes

    def build_subgraph(self, segments: list[PathSegment]) -> tuple[list[GraphNode], list[GraphEdge]]:
        node_ids: set[str] = set()
        edge_ids: set[str] = set()
        for seg in segments:
            for eid in (
                seg.factor_element_id,
                seg.condition_element_id,
                seg.mediator_element_id,
                seg.chunk_element_id,
            ):
                if eid:
                    node_ids.add(eid)
            for eid in (
                seg.relationship_element_id,
                seg.contributes_element_id,
                seg.describes_element_id,
                seg.applies_element_id,
            ):
                if eid:
                    edge_ids.add(eid)

        nodes = self.fetch_nodes_by_element_ids(sorted(node_ids))
        if not edge_ids:
            return nodes, []

        cypher = """
        UNWIND $ids AS eid
        MATCH ()-[r]->()
        WHERE elementId(r) = eid
        RETURN
          elementId(r) AS element_id,
          type(r) AS rel_type,
          elementId(startNode(r)) AS start_id,
          elementId(endNode(r)) AS end_id,
          properties(r) AS props
        """
        edges: list[GraphEdge] = []
        for row in self._run(cypher, ids=sorted(edge_ids)):
            edges.append(
                edge_from_record(
                    element_id=row["element_id"],
                    rel_type=row["rel_type"],
                    start_element_id=row["start_id"],
                    end_element_id=row["end_id"],
                    properties=dict(row["props"] or {}),
                )
            )
        return merge_elements(nodes, edges)


# Backward-compatible alias for Graphs/ scripts.
GraphClient = Neo4jGraphClient
