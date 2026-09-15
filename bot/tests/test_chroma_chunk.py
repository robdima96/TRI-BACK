"""Look up one ingested chunk by ``chunk_id`` across Chroma sub-collections.

Chunk IDs are unique across sub-collections; the script scans each collection
until a match is found.

Run from the repo root::

    python tests/test_chroma_chunk.py r_5
    python tests/test_chroma_chunk.py r_5 --chroma-path data/chroma

Exit codes: 0 found, 1 not found, 2 usage/config error.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


@dataclass(frozen=True)
class ChromaChunkHit:
    chunk_id: str
    sub_collection: str
    text: str
    metadata: dict[str, str]


def lookup_chroma_chunk(chunk_id: str) -> ChromaChunkHit | None:
    """Return chunk text and metadata, or ``None`` if ``chunk_id`` is not in Chroma."""
    from app.services.rag.store import get_sub_collection, list_sub_collections

    key = (chunk_id or "").strip()
    if not key:
        return None

    for name in list_sub_collections():
        coll = get_sub_collection(name)
        if coll.count() == 0:
            continue
        res = coll.get(ids=[key], include=["documents", "metadatas"])
        ids = res.get("ids") or []
        if not ids:
            continue
        docs = res.get("documents") or [""]
        metas = res.get("metadatas") or [{}]
        text = docs[0] if docs else ""
        raw_meta = metas[0] if metas else {}
        metadata = _stringify_metadata(raw_meta)
        return ChromaChunkHit(
            chunk_id=key,
            sub_collection=name,
            text=text or "",
            metadata=metadata,
        )
    return None


def _stringify_metadata(meta: dict[str, Any] | None) -> dict[str, str]:
    if not meta:
        return {}
    out: dict[str, str] = {}
    for key, val in meta.items():
        if val is None:
            continue
        out[str(key)] = str(val)
    return dict(sorted(out.items()))


def format_chunk_output(hit: ChromaChunkHit) -> str:
    """Human-readable output with chunk text and metadata in separate sections."""
    lines = [
        f"chunk_id: {hit.chunk_id}",
        f"sub_collection: {hit.sub_collection}",
        "",
        "CHUNK_TEXT:",
        hit.text,
        "",
        "METADATA:",
    ]
    if hit.metadata:
        for key, val in hit.metadata.items():
            lines.append(f"{key}: {val}")
    else:
        lines.append("(none)")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s %(message)s",
    )
    logging.getLogger("chromadb").setLevel(logging.WARNING)

    parser = argparse.ArgumentParser(
        description="Fetch one Chroma chunk by chunk_id (text and metadata).",
    )
    parser.add_argument(
        "chunk_id",
        help="Document id stored in Chroma (e.g. r_5, red_flags_2_0001)",
    )
    parser.add_argument(
        "--chroma-path",
        metavar="PATH",
        help="Override DIGIMSK_CHROMA_PATH for this run only",
    )
    args = parser.parse_args(argv)

    if args.chroma_path:
        os.environ["DIGIMSK_CHROMA_PATH"] = args.chroma_path

    from app.config import settings

    if not settings.rag_load:
        logging.error("RAG is disabled (set TRI_BACK_LOAD_RAG=1).")
        return 2

    chunk_id = args.chunk_id.strip()
    if not chunk_id:
        logging.error("chunk_id must be non-empty.")
        return 2

    logging.info("Chroma path: %s", Path(settings.chroma_persist_path).resolve())
    hit = lookup_chroma_chunk(chunk_id)
    if hit is None:
        logging.error("No chunk found for chunk_id=%r.", chunk_id)
        return 1

    print(format_chunk_output(hit))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
