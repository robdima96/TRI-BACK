"""Fill evidence and evidence_level on a manual chunk registry from the sources catalog.



Run from repo root::



    python scripts/enrich_chunk_evidence.py

    python scripts/enrich_chunk_evidence.py --kb-dir "Knowledge Base/Red Flags"

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

    from app.services.rag.chunk_and_ingest import (

        default_kb_dir,

        enrich_chunk_registry_evidence,

        resolve_manual_chunks_csv,

        resolve_kb_paths,

    )



    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")



    parser = argparse.ArgumentParser(

        description="Fill evidence columns on a manual chunk registry from the sources catalog.",

    )

    parser.add_argument(

        "--kb-dir",

        type=Path,

        default=None,

        help="Knowledge-base root (default: Knowledge Base/Red Flags).",

    )

    parser.add_argument(

        "--chunks-csv",

        type=Path,

        default=None,

        help="Manual registry CSV (default: <kb_dir>/chunks/manual/<slug>_manual.csv).",

    )

    parser.add_argument(

        "--sources-dir",

        type=Path,

        default=None,

        help="Sources catalog directory (default: <kb_dir>/sources).",

    )

    args = parser.parse_args()



    kb_dir = (args.kb_dir or default_kb_dir(_ROOT)).resolve()

    _, sources_dir, _ = resolve_kb_paths(kb_dir, registry="manual")

    chunks_csv = (

        args.chunks_csv or resolve_manual_chunks_csv(kb_dir)

    ).resolve()

    sources_dir = (args.sources_dir or sources_dir).resolve()



    if not chunks_csv.is_file():

        print(f"Chunk registry not found: {chunks_csv}", file=sys.stderr)

        return 2

    return enrich_chunk_registry_evidence(

        chunks_csv=chunks_csv,

        sources_dir=sources_dir,

    )





if __name__ == "__main__":

    raise SystemExit(main())


