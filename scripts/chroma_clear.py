"""Clear or delete evidence sub-collections in persisted Chroma.



Run from repo root::



    python scripts/chroma_clear.py --empty

    python scripts/chroma_clear.py



Uses ``DIGIMSK_CHROMA_PATH`` via ``settings``.



``--empty`` removes all documents but keeps each sub-collection (recommended before

re-ingest with a new embedding model). Without ``--empty``, deletes collections entirely.



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

    parser = argparse.ArgumentParser(

        description="Clear or remove RAG evidence Chroma sub-collections.",

    )

    parser.add_argument(

        "--empty",

        action="store_true",

        help="Delete all documents inside each sub-collection; keep collections.",

    )

    parser.add_argument(

        "--dry-run",

        action="store_true",

        help="Print path and collection names only; do not modify Chroma.",

    )

    args = parser.parse_args()



    from app.config import settings

    from app.services.rag.store import (

        EVIDENCE_SUB_COLLECTIONS,

        clear_all_sub_collection_documents,

    )



    _legacy_names = (

        "Red Flags",

        "Clinical Guidelines",

        "Clinical Vignettes",

        "Conversation Templates",

        "Diagnostic Confounders",

    )

    targets = tuple(dict.fromkeys((*EVIDENCE_SUB_COLLECTIONS, *_legacy_names)))



    persist = Path(settings.chroma_persist_path)

    print(f"Chroma path: {persist.resolve()}")

    for name in targets:

        print(f"  sub-collection: {name!r}")



    if args.dry_run:

        print("Dry run: nothing changed.")

        return 0



    if args.empty:

        counts = clear_all_sub_collection_documents()

        total = sum(counts.values())

        for name, n in counts.items():

            print(f"Emptied {name!r}: {n} document(s) removed.")

        print(f"Total documents removed: {total}. Repopulate via ingest before relying on RAG.")

        return 0



    import chromadb

    from chromadb.errors import NotFoundError



    client = chromadb.PersistentClient(

        path=str(persist.resolve()),

        settings=chromadb.Settings(anonymized_telemetry=False),

    )

    deleted = 0

    for name in targets:

        try:

            client.delete_collection(name)

            print(f"Deleted collection {name!r}.")

            deleted += 1

        except NotFoundError:

            print(f"Collection {name!r} already absent.")

    if deleted:

        print("Repopulate via ingest before relying on RAG.")

    return 0





if __name__ == "__main__":

    raise SystemExit(main())

