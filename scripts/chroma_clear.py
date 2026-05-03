"""Delete the evidence collection from persisted Chroma (next open re-seeds if empty).

Run from repo root::

    python scripts/chroma_clear.py

Uses ``DIGIMSK_CHROMA_PATH`` / ``DIGIMSK_CHROMA_COLLECTION`` via ``settings``.

If uvicorn or another process has Chroma open, stop it first to avoid SQLITE_BUSY.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description="Remove the RAG evidence Chroma collection.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print path and collection name only; do not delete.",
    )
    args = parser.parse_args()

    import chromadb
    from chromadb.errors import NotFoundError

    from app.config import settings

    persist = Path(settings.chroma_persist_path)
    coll_name = settings.chroma_collection_name
    print(f"Chroma path: {persist.resolve()}")
    print(f"Collection:  {coll_name!r}")

    if args.dry_run:
        print("Dry run: nothing deleted.")
        return 0

    client = chromadb.PersistentClient(
        path=str(persist.resolve()),
        settings=chromadb.Settings(anonymized_telemetry=False),
    )
    try:
        client.delete_collection(coll_name)
    except NotFoundError:
        print(f"Collection {coll_name!r} is already absent; nothing to delete.")
        return 0
    print(
        f"Deleted collection {coll_name!r}. Next ingest or app open seeds "
        "_DEFAULT_CHUNKS if recreated empty."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
