"""Chroma persistent store: collection init and dev seeding.

For ingestion of new chunks, call :meth:`~chromadb.Collection.add` to index text chunks with
embeddings from the same model as :func:`app.services.rag.embeddings.compute_query_embedding`;
embedding dimension must match ``Settings.encoder_embedding_dim``. NER metadata can be
attached per chunk in ``metadatas``.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any

import chromadb
import numpy as np
from chromadb.api import Collection

from app.config import settings

_log = logging.getLogger(__name__)

# cached client and collection handles 
_chroma: chromadb.PersistentClient | None = None
_collection: Collection | None = None

# Placeholder guidelines for empty DB dev/tests
_DEFAULT_CHUNKS: list[tuple[str, str, dict[str, Any]]] = [
    (
        "chunk_1",
        (
            "Superficial heat (application of heating pads or heated blankets) is "
            "recommended for the short term relief of acute low back pain. "
            "Clinical experience supports a role for superficial cold packs and alternating "
            "heat and cold as per patient preference. "
            "Heat or cold should not be applied directly to the skin, and not for longer than "
            "15 to 20 minutes. Use with care if lack of protective sensation."
        ),
        {
            "source": "Evidence-Informed Primary Care Guideline for Management of Low Back Pain",
            "section": "treatment",
        },
    ),
    (
        "chunk_2",
        (
            "Many people with new low back pain improve over days to weeks without treatment. "
            "Red flags such as major trauma, fever, history of cancer, or progressive neurological "
            "symptoms like numbness or tingling require urgent in-person care."
        ),
        {
            "source": "Evidence-Informed Primary Care Guideline for Management of Low Back Pain",
            "section": "prognosis",
        },
    ),
    (
        "chunk_3",
        (
            "Reassess patients whose symptoms are not resolving. Follow-up in 1 week if "
            "pain is severe and has not subsided. Follow-up in 3 weeks if moderate pain is "
            "not improving. Follow-up in 6 weeks if not substantially recovered."
        ),
        {
            "source": "Evidence-Informed Primary Care Guideline for Management of Low Back Pain",
            "section": "follow-up",
        },
    ),
]

'''
def _stable_unit_embedding(text: str, dim: int) -> list[float]:
    """Reproducible 768-d unit vector (for dev seed only, not a clinical encoder)."""
    seed = int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:8], 16) % (2**31)
    rng = np.random.default_rng(seed)
    v = rng.standard_normal(dim, dtype=np.float64)
    n = float(np.linalg.norm(v)) + 1e-9
    v = (v / n).astype(np.float32)
    return v.tolist()
'''

# get persistent client for Chroma and set local path
def get_chroma_client() -> chromadb.PersistentClient:
    global _chroma
    if _chroma is None:
        path = settings.chroma_persist_path
        _chroma = chromadb.PersistentClient(
            path=path,
            settings=chromadb.Settings(anonymized_telemetry=False), # disable telemetry
        )
        _log.info("Chroma persistent client at %s", path)
    return _chroma


def get_evidence_collection() -> Collection:
    global _collection
    if _collection is None:
        client = get_chroma_client()
        _collection = client.get_or_create_collection(
            name=settings.chroma_collection_name,
            metadata={"hnsw:space": "cosine"}, # use cosine similarity for retrieval
        )
        # dev behaviour: seed with _DEFAULT_CHUNKS if collection is empty
        if _collection.count() == 0:
            _seed_default_chunks(_collection)
    return _collection

# dev behaviour: seed with _DEFAULT_CHUNKS if collection is empty
def _seed_default_chunks(collection: Collection) -> None:
    dim = settings.encoder_embedding_dim
    ids: list[str] = []
    documents: list[str] = []
    metadatas: list[dict[str, Any]] = []
    embeddings: list[list[float]] = []
    for chunk_id, text, meta in _DEFAULT_CHUNKS:
        ids.append(chunk_id)
        documents.append(text)
        metadatas.append({**meta, "chunk_id": chunk_id})
        embeddings.append(_stable_unit_embedding(text, dim))
    # add the chunks to the collection
    # add and not upsert, only runs when collection is empty
    collection.add(
        ids=ids,
        documents=documents,
        metadatas=metadatas,
        embeddings=embeddings,
    )
    _log.info("Seeded Chroma with %d default MSK chunks (dev)", len(ids))


def reset_collection_for_tests() -> None:
    """Drop cached handles so a new test directory can be used (internal/tests only)."""
    global _chroma, _collection
    _chroma = None
    _collection = None
