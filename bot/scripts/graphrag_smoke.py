#!/usr/bin/env python3
"""Smoke test: encoder checklist + chunk retrieval + local graph traversal."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.schemas import ChecklistItem
from app.services.encoder import encode_user_message
from app.services.gliner_ner import gliner_configured, gliner_model_dir
from app.services.graphrag import graphrag_configured, traverse_from_turn
from app.services.rag.chunk_retrieval import retrieve_rag_chunk_matches
from app.services.rag.fusion import build_traversal_seeds


def main() -> int:
    parser = argparse.ArgumentParser(
        description="GraphRAG smoke test (local v1 CSV; no Neo4j)."
    )
    parser.add_argument(
        "message",
        nargs="?",
        default="I am 70 with severe pain after a recent fall.",
    )
    parser.add_argument("--json", action="store_true", help="Print full trace JSON")
    args = parser.parse_args()

    gliner_dir = gliner_model_dir()
    print(f"GliNER dir:  {gliner_dir}")
    print(f"GliNER ok:   {gliner_configured()}")
    print(f"Graph CSV:   {graphrag_configured()}")

    enc = encode_user_message(args.message)
    items = enc.checklist.items
    print(f"Message: {args.message!r}")
    print(f"Checklist items: {len(items)}")
    for it in items:
        print(f"  - [{it.source}/{it.kind}] {it.text!r} ({it.label})")

    from app.config import settings

    chunk_matches = []
    if settings.rag_load:
        chunk_matches = retrieve_rag_chunk_matches(
            args.message,
            enc.pooled_embedding or None,
            items,
        )

    seeds = build_traversal_seeds(
        checklist=items,
        chunk_matches=chunk_matches,
    )
    print(f"\nMatched factors (leg A): {seeds.matched_factor_names}")
    print(f"Chunk matches (leg B): {[c.chunk_id for c in seeds.chunk_matches]}")

    trace = traverse_from_turn(
        checklist=items,
        chunk_matches=seeds.chunk_matches,
        factor_matches=seeds.factor_matches,
        title=f"Smoke: {args.message[:60]}",
    )

    print(f"\nTrace id: {trace.trace_id}")
    print(f"Candidate conditions: {trace.candidate_conditions}")
    print(f"Steps: {len(trace.steps)}")
    print(f"Subgraph: {len(trace.nodes)} nodes, {len(trace.edges)} edges")

    print("\n--- Steps ---")
    for step in trace.steps:
        extra = ""
        if step.factor:
            extra += f" factor={step.factor!r}"
        if step.condition:
            extra += f" condition={step.condition!r}"
        if step.chunk_id:
            extra += f" chunk={step.chunk_id!r}"
        print(f"  {step.step:02d} {step.action}{extra}: {step.note or ''}")

    if args.json:
        print("\n--- JSON ---")
        print(json.dumps(trace.model_dump(), indent=2, ensure_ascii=False))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
