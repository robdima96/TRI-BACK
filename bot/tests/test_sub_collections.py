"""Evidence sub-collection validation and chunk registry paths.

Run from the repo root::

    python tests/test_sub_collections.py list
    python tests/test_sub_collections.py validate "Red Flags"
    python tests/test_sub_collections.py paths
    python tests/test_sub_collections.py counts

Exit codes: 0 ok, 1 validation/lookup error, 2 usage/config error.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.services.rag.chunk_and_ingest import (
    default_kb_dir,
    detect_registry_format,
    manual_registry_filename,
    resolve_extracted_chunks_csv,
    resolve_manual_chunks_csv,
)
from app.services.rag.store import (
    EVIDENCE_SUB_COLLECTIONS,
    get_sub_collection,
    list_sub_collections,
    validate_sub_collection,
)


def test_validate_sub_collection_accepts_canonical_names():
    for name in EVIDENCE_SUB_COLLECTIONS:
        assert validate_sub_collection(name) == name


def test_validate_sub_collection_accepts_display_style_aliases():
    assert validate_sub_collection("Red Flags") == "red_flags"
    assert validate_sub_collection("clinical guidelines") == "clinical_guidelines"


def test_validate_sub_collection_rejects_unknown():
    with pytest.raises(ValueError, match="Unknown sub-collection"):
        validate_sub_collection("digimsk_evidence")


def test_chunk_registry_paths_and_format_detection():
    kb = Path("Knowledge Base/Red Flags")
    assert resolve_extracted_chunks_csv(kb).name == "red_flags_extracted.csv"
    assert resolve_manual_chunks_csv(kb).name == manual_registry_filename(kb)
    assert detect_registry_format(["chunk_id", "chunk_string", "evidence"]) == "manual"
    assert detect_registry_format(
        ["chunk_id", "chunk_string", "source", "metadata_tags"]
    ) == "extracted"


def _cmd_list() -> int:
    for name in list_sub_collections():
        print(name)
    return 0


def _cmd_validate(name: str) -> int:
    slug = validate_sub_collection(name)
    print(slug)
    return 0


def _cmd_paths(kb_dir: Path) -> int:
    extracted = resolve_extracted_chunks_csv(kb_dir)
    manual = resolve_manual_chunks_csv(kb_dir)
    print(f"kb_dir: {kb_dir.resolve()}")
    print(f"extracted: {extracted.resolve()}")
    print(f"manual: {manual.resolve()}")
    if extracted.is_file():
        print(f"extracted_format: {detect_registry_format_from_csv(extracted)}")
    if manual.is_file():
        print(f"manual_format: {detect_registry_format_from_csv(manual)}")
    return 0


def detect_registry_format_from_csv(path: Path) -> str:
    import csv

    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
    return detect_registry_format(fieldnames)


def _cmd_counts(chroma_path: str | None) -> int:
    if chroma_path:
        os.environ["DIGIMSK_CHROMA_PATH"] = chroma_path

    from app.config import settings

    if not settings.rag_load:
        logging.error("RAG is disabled (set DIGIMSK_LOAD_RAG=1).")
        return 2

    persist = Path(settings.chroma_persist_path).resolve()
    print(f"chroma_path: {persist}")
    for name in list_sub_collections():
        coll = get_sub_collection(name)
        print(f"{name}: {coll.count()}")
    return 0


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s %(message)s",
    )
    logging.getLogger("chromadb").setLevel(logging.WARNING)

    parser = argparse.ArgumentParser(
        description="Sub-collection slugs, validation, registry paths, Chroma counts.",
    )
    parser.add_argument(
        "--chroma-path",
        metavar="PATH",
        help="Override DIGIMSK_CHROMA_PATH (counts command only)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="Print configured Chroma sub-collection slugs")

    p_validate = sub.add_parser(
        "validate",
        help="Normalize a sub-collection name to its Chroma slug",
    )
    p_validate.add_argument(
        "name",
        help='Slug or display label (e.g. red_flags, "Red Flags")',
    )

    p_paths = sub.add_parser(
        "paths",
        help="Resolve extracted/manual chunk registry CSV paths for a KB folder",
    )
    p_paths.add_argument(
        "--kb-dir",
        type=Path,
        default=None,
        help="Knowledge-base root (default: Knowledge Base/Red Flags)",
    )

    sub.add_parser(
        "counts",
        help="Document count per sub-collection in persisted Chroma",
    )

    args = parser.parse_args(argv)

    try:
        if args.command == "list":
            return _cmd_list()
        if args.command == "validate":
            return _cmd_validate(args.name)
        if args.command == "paths":
            kb = args.kb_dir or default_kb_dir()
            return _cmd_paths(kb)
        if args.command == "counts":
            return _cmd_counts(args.chroma_path)
    except ValueError as exc:
        logging.error("%s", exc)
        return 1

    logging.error("Unknown command %r", args.command)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
