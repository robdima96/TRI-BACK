#!/usr/bin/env python3
"""Export an interactive HTML visualization of the red-flags graph."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from pyvis.network import Network

from config import GRAPHS_DIR
from neo4j_client import Neo4jConfig

OUTPUT_DIR = GRAPHS_DIR / "output"

NODE_COLORS = {
    "Factor": "#4C9AFF",
    "Condition": "#FF6B6B",
    "Chunk": "#6BCB77",
}

EDGE_COLORS = {
    "CONTRIBUTES_TO": "#888888",
    "DESCRIBES": "#444444",
    "APPLIES_TO": "#444444",
}


def fetch_subgraph(condition: str | None, limit: int) -> tuple[list[dict], list[dict]]:
    config = Neo4jConfig.from_env()
    config.validate()
    driver = config.driver()
    if condition:
        cypher = """
        MATCH (c:Condition {name: $condition})
        CALL {
            WITH c
            MATCH p = (c)-[*1..2]-(n)
            RETURN nodes(p) AS ns, relationships(p) AS rs
            LIMIT $limit
        }
        UNWIND ns AS node
        UNWIND rs AS rel
        RETURN collect(DISTINCT node) AS nodes, collect(DISTINCT rel) AS rels
        """
        params = {"condition": condition, "limit": limit}
    else:
        cypher = """
        MATCH (n)
        WHERE n:Factor OR n:Condition
        WITH collect(n)[..$node_cap] AS node_subset
        UNWIND node_subset AS n
        OPTIONAL MATCH (n)-[r]-(m)
        WHERE m IN node_subset
        RETURN collect(DISTINCT n) AS nodes, collect(DISTINCT r) AS rels
        """
        params = {"node_cap": min(limit, 120)}

    with driver.session(database=config.database) as session:
        record = session.run(cypher, params).single()
    driver.close()

    nodes = [_node_payload(n) for n in (record["nodes"] or []) if n is not None]
    edges = [_edge_payload(r) for r in (record["rels"] or []) if r is not None]
    return nodes, edges


def _node_payload(node) -> dict:
    labels = list(node.labels)
    label = labels[0] if labels else "Node"
    name = node.get("name") or node.get("chunk_id") or str(node.element_id)
    title = name
    if label == "Chunk":
        text = node.get("chunk_string", "")
        title = f"{name}\n\n{text[:400]}{'...' if len(text) > 400 else ''}"
    return {
        "id": node.element_id,
        "label": name if len(name) < 36 else name[:33] + "...",
        "title": title,
        "group": label,
        "color": NODE_COLORS.get(label, "#AAAAAA"),
    }


def _edge_payload(rel) -> dict:
    rel_type = rel.type
    props = dict(rel)
    title = rel_type
    if props:
        title += "\n" + json.dumps(props, indent=2)
    return {
        "from": rel.start_node.element_id,
        "to": rel.end_node.element_id,
        "label": rel_type,
        "title": title,
        "color": EDGE_COLORS.get(rel_type, "#BBBBBB"),
        "arrows": "to",
    }


def build_html(nodes: list[dict], edges: list[dict], out_path: Path) -> None:
    net = Network(height="800px", width="100%", directed=True, bgcolor="#1a1a2e", font_color="#eeeeee")
    net.barnes_hut(gravity=-8000, central_gravity=0.3, spring_length=120)
    for node in nodes:
        net.add_node(
            node["id"],
            label=node["label"],
            title=node["title"],
            color=node["color"],
            group=node["group"],
        )
    for edge in edges:
        net.add_edge(
            edge["from"],
            edge["to"],
            label=edge["label"],
            title=edge["title"],
            color=edge["color"],
            arrows=edge["arrows"],
        )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    net.write_html(str(out_path), open_browser=False)


def main() -> int:
    parser = argparse.ArgumentParser(description="Export Neo4j subgraph to interactive HTML")
    parser.add_argument("--condition", help="Focus on one Condition node (e.g. Fracture)")
    parser.add_argument("--limit", type=int, default=200, help="Max paths / nodes to include")
    parser.add_argument(
        "--output",
        type=Path,
        default=OUTPUT_DIR / "red_flags_graph.html",
        help="Output HTML path",
    )
    args = parser.parse_args()

    nodes, edges = fetch_subgraph(args.condition, args.limit)
    build_html(nodes, edges, args.output)
    print(f"Wrote {len(nodes)} nodes, {len(edges)} edges -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
