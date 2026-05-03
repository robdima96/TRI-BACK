"""Smoke-test RAG end-to-end: local encoder embedding -> Chroma -> retrieve_evidence.

Run from the repo root (``bot``) so imports and relative paths resolve::

    python scripts/rag_smoke.py
    python scripts/rag_smoke.py --query "heat therapy for low back pain"

Expect ``DIGIMSK_LOAD_RAG=1`` (default) and a valid ``DIGIMSK_ENCODER_DIR`` with
either ``config.json`` (HF layout), optional nested ``encoder/``/``backbone/`` ...
with ``config.json``, **or** GliNER-style ``gliner_config.json`` (loads ``model_name``
backbone via Hugging Face). Chroma uses ``DIGIMSK_CHROMA_PATH``; an empty DB is auto-seeded
with default guideline chunks.

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


def main() -> int:
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(levelname)s %(name)s %(message)s",
    )
    logging.getLogger("chromadb").setLevel(logging.WARNING)

    parser = argparse.ArgumentParser(description="RAG smoke (encoder + Chroma + retrieval).")
    parser.add_argument(
        "--query",
        default="superficial heat for acute low back pain",
        help="Query text to embed and search",
    )
    args = parser.parse_args()

    from app.config import settings
    from app.services.rag import retrieve_evidence
    from app.services.rag.embeddings import (
        compute_query_embedding,
        rag_embedding_model_configured,
    )
    from app.services.rag.store import get_evidence_collection

    if not settings.rag_load:
        logging.error("RAG is disabled (set DIGIMSK_LOAD_RAG=1).")
        return 1
    if not rag_embedding_model_configured():
        logging.error(
            "Encoder layout invalid — need ``config.json`` (optionally under "
            "``encoder/``/``backbone/``/) or ``gliner_config.json`` with "
            "``model_name``: %s",
            settings.encoder_model_dir,
        )
        return 1

    coll = get_evidence_collection()
    logging.info(
        "Chroma %r at %s — document count=%s",
        settings.chroma_collection_name,
        settings.chroma_persist_path,
        coll.count(),
    )

    emb = compute_query_embedding(args.query)
    if len(emb) != settings.encoder_embedding_dim:
        logging.error(
            "Embedding length %s (expected %s); encoder may have failed.",
            len(emb),
            settings.encoder_embedding_dim,
        )
        return 1

    rows = retrieve_evidence(args.query, emb, top_k=settings.rag_top_k)
    if not rows:
        logging.warning("retrieve_evidence returned no rows.")
        return 2

    for i, ev in enumerate(rows, 1):
        snippet = ev.snippet.replace("\n", " ")
        tail = "..." if len(snippet) > 280 else ""
        print(f"{i}. score={ev.score:.4f} source={ev.source!r}")
        print(f"   {snippet[:280]}{tail}")

    logging.info("RAG smoke OK (%d hits).", len(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
