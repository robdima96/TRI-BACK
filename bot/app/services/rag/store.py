"""Chroma persistent store: sub-collection init and lookup.

For ingestion, use :func:`app.services.rag.ingest_evidence_chunk` with a
``sub_collection`` from :data:`EVIDENCE_SUB_COLLECTIONS` (Chroma-safe slugs).
Embeddings must match ``Settings.encoder_embedding_dim`` (Clinical_sBERT / query encoding).
"""

from __future__ import annotations

import logging
import re

import chromadb
from chromadb.api import Collection

from app.config import settings

_log = logging.getLogger(__name__)

# Chroma collection names: [a-zA-Z0-9._-], 3-512 chars, no spaces.
EVIDENCE_SUB_COLLECTIONS: tuple[str, ...] = (
    "red_flags",
    "clinical_guidelines",
    "clinical_vignettes",
    "conversation_templates",
    "diagnostic_confounders",
)

_COLLECTION_METADATA = {"hnsw:space": "cosine"}

_chroma: chromadb.PersistentClient | None = None
_collections: dict[str, Collection] = {}


def _slugify_sub_collection(name: str) -> str:
    """Map CLI input to a Chroma-safe slug (e.g. ``Red Flags`` -> ``red_flags``)."""
    return re.sub(r"[^a-zA-Z0-9]+", "_", name.strip()).lower().strip("_")


def validate_sub_collection(name: str) -> str:
    """Return the canonical Chroma sub-collection slug or raise ``ValueError``."""
    key = (name or "").strip()
    if key in EVIDENCE_SUB_COLLECTIONS:
        return key
    slug = _slugify_sub_collection(key)
    if slug in EVIDENCE_SUB_COLLECTIONS:
        return slug
    allowed = ", ".join(EVIDENCE_SUB_COLLECTIONS)
    raise ValueError(f"Unknown sub-collection {name!r}; allowed: {allowed}")


def get_chroma_client() -> chromadb.PersistentClient:
    global _chroma
    if _chroma is None:
        path = settings.chroma_persist_path
        _chroma = chromadb.PersistentClient(
            path=path,
            settings=chromadb.Settings(anonymized_telemetry=False),
        )
        _log.info("Chroma persistent client at %s", path)
    return _chroma


def get_sub_collection(sub_collection: str) -> Collection:
    """Get or create one evidence sub-collection by slug."""
    canonical = validate_sub_collection(sub_collection)
    cached = _collections.get(canonical)
    if cached is not None:
        return cached
    client = get_chroma_client()
    coll = client.get_or_create_collection(
        name=canonical,
        metadata=_COLLECTION_METADATA,
    )
    _collections[canonical] = coll
    return coll


def list_sub_collections() -> list[str]:
    """Return all configured sub-collection slugs."""
    return list(EVIDENCE_SUB_COLLECTIONS)


def clear_sub_collection_documents(sub_collection: str) -> int:
    """Remove all documents from a sub-collection; keep the collection itself."""
    from app.services.rag.chunk_retrieval import invalidate_lexical_doc_index

    coll = get_sub_collection(sub_collection)
    total = 0
    batch_size = 500
    while True:
        result = coll.get(limit=batch_size, include=[])
        ids = result.get("ids") or []
        if not ids:
            break
        coll.delete(ids=ids)
        total += len(ids)
        if len(ids) < batch_size:
            break
    invalidate_lexical_doc_index()
    _log.info("Cleared %d document(s) from sub-collection %r", total, sub_collection)
    return total


def clear_all_sub_collection_documents() -> dict[str, int]:
    """Empty every configured evidence sub-collection without deleting collections."""
    counts: dict[str, int] = {}
    for name in EVIDENCE_SUB_COLLECTIONS:
        counts[name] = clear_sub_collection_documents(name)
    return counts


def reset_collection_for_tests() -> None:
    """Drop cached handles so a new test directory can be used (internal/tests only)."""
    global _chroma, _collections
    _chroma = None
    _collections = {}
