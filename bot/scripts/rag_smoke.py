"""Smoke-test RAG end-to-end: local encoder embedding -> Chroma -> retrieval.

Run from the repo root (``bot``) so imports and relative paths resolve::

    python scripts/rag_smoke.py
    python scripts/rag_smoke.py --query "heat therapy for low back pain"

Expect ``TRI_BACK_LOAD_RAG=1`` (default; legacy ``TRI_BACK_LOAD_RAG``) and a valid ``TRI_BACK_ENCODER_DIR`` (Clinical_sBERT
folder with ``config.json``; ``sentence_transformers`` backend by default). Chroma uses
``TRI_BACK_CHROMA_PATH``; sub-collections must already contain ingested chunks (re-ingest
after model changes via ``scripts/chroma_clear.py --empty``).

Exit codes: 0 ok, 1 config/embedding failure, 2 no retrieval rows.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _configure_logging(*, verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.WARNING,
        format="%(levelname)s %(name)s %(message)s",
        force=True,
    )
    for name in (
        "chromadb",
        "httpx",
        "httpcore",
        "huggingface_hub",
        "urllib3",
        "transformers",
        "filelock",
        "gliner",
        "sentence_transformers",
        "tqdm",
    ):
        logging.getLogger(name).setLevel(logging.ERROR if not verbose else logging.WARNING)


def _distance_to_score(d: float) -> float:
    return max(0.0, min(1.0, 1.0 / (1.0 + max(0.0, d))))


def _collect_hits(
    query_embedding: list[float],
    top_k: int,
) -> list[tuple[str, str, float, str]]:
    """Query each non-empty sub-collection; merge by ``chunk_id``, keep best score."""
    from app.services.rag.store import get_sub_collection, list_sub_collections, validate_sub_collection

    best_by_id: dict[str, tuple[str, str, float, str]] = {}
    for name in list_sub_collections():
        canonical = validate_sub_collection(name)
        coll = get_sub_collection(canonical)
        count = coll.count()
        if count == 0:
            continue
        n_results = min(top_k, max(1, count))
        res = coll.query(
            query_embeddings=[query_embedding],
            n_results=n_results,
            include=["distances", "documents"],
        )
        ids0 = res["ids"][0] if res["ids"] else []
        dists0 = res["distances"][0] if res.get("distances") else [0.0] * len(ids0)
        docs0 = res["documents"][0] if res.get("documents") else [""] * len(ids0)
        for chunk_id, d, doc in zip(ids0, dists0, docs0):
            score = _distance_to_score(float(d))
            text = doc if doc is not None else ""
            prev = best_by_id.get(chunk_id)
            if prev is None or score > prev[2]:
                best_by_id[chunk_id] = (chunk_id, canonical, score, text)

    hits = list(best_by_id.values())
    hits.sort(key=lambda h: h[2], reverse=True)
    return hits[:top_k]


def _format_report(
    *,
    query: str,
    top_k: int,
    chroma_path: str,
    collection_counts: list[tuple[str, int]],
    hits: list[tuple[str, str, float, str]],
) -> str:
    lines: list[str] = [
        f"query: {query!r}",
        f"top_k: {top_k}",
        f"chroma_path: {chroma_path}",
    ]
    for name, count in collection_counts:
        lines.append(f"  {name!r}: {count} document(s)")
    if not hits:
        lines.append("")
        lines.append("(no retrieval hits)")
        return "\n".join(lines)

    for i, (chunk_id, sub_collection, score, text) in enumerate(hits, 1):
        lines.append("")
        lines.append(
            f"--- {i}. chunk_id={chunk_id} "
            f"sub_collection={sub_collection} score={score:.4f} ---"
        )
        lines.append(text)
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="RAG smoke (encoder + Chroma + retrieval).")
    parser.add_argument(
        "--query",
        default="superficial heat for acute low back pain",
        help="Query text to embed and search",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable DEBUG logs (includes Hugging Face HTTP trace noise)",
    )
    args = parser.parse_args()
    _configure_logging(verbose=args.verbose)

    from app.config import settings
    from app.services.rag.embeddings import (
        compute_query_embedding,
        rag_embedding_model_configured,
    )
    from app.services.rag.store import get_sub_collection, list_sub_collections

    if not settings.rag_load:
        sys.stderr.write("RAG is disabled (set TRI_BACK_LOAD_RAG=1).\n")
        return 1
    if not rag_embedding_model_configured():
        sys.stderr.write(
            f"Encoder layout invalid — check TRI_BACK_ENCODER_DIR: "
            f"{settings.encoder_model_dir}\n"
        )
        return 1

    collection_counts: list[tuple[str, int]] = []
    for name in list_sub_collections():
        collection_counts.append((name, get_sub_collection(name).count()))

    emb = compute_query_embedding(args.query)
    if len(emb) != settings.encoder_embedding_dim:
        sys.stderr.write(
            f"Embedding length {len(emb)} (expected {settings.encoder_embedding_dim}).\n"
        )
        return 1

    k = settings.rag_top_k
    hits = _collect_hits(emb, k)
    report = _format_report(
        query=args.query,
        top_k=k,
        chroma_path=str(Path(settings.chroma_persist_path).resolve()),
        collection_counts=collection_counts,
        hits=hits,
    )
    sys.stdout.write(report + "\n")
    sys.stdout.flush()

    if not hits:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
