"""Chunk knowledge-base PDFs and (separately) ingest a reviewed chunk registry.

Each knowledge-base **root folder** must follow the same layout as
``Knowledge Base/Red Flags``::

    <kb_dir>/docs/              — source PDFs named ``{source_id}.pdf`` (e.g. ``1.pdf``)
    <kb_dir>/sources/           — ``*.csv`` or ``*.xlsx`` catalog (``source_id`` column)
    <kb_dir>/chunks/extracted/  — PDF auto-chunk CSV (review before ingest)
    <kb_dir>/chunks/manual/     — hand-curated chunk CSV (review before ingest)

Workflow:

1. :func:`run_chunk_catalog` — auto-extract PDFs → ``chunks/extracted/<slug>_extracted.csv``
2. Edit / author rows in ``chunks/manual/<slug>_manual.csv`` (and enrich evidence)
3. :func:`ingest_chunks_from_csv` — upsert a reviewed CSV into a Chroma sub-collection

CLI::

    python scripts/extract_chunks.py --kb-dir "Knowledge Base/Red Flags"
    python scripts/ingest_chunks.py --sub-collection red_flags --registry extracted
    python scripts/ingest_chunks.py --sub-collection red_flags --registry manual
    python scripts/enrich_chunk_evidence.py --kb-dir "Knowledge Base/Red Flags"
"""

from __future__ import annotations

import csv
import hashlib
import logging
import re
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Any, Literal

RegistryFormat = Literal["extracted", "manual", "auto"]

_log = logging.getLogger(__name__)

CSV_FIELDNAMES = ("chunk_id", "chunk_string", "source", "metadata_tags")

DOCS_SUBDIR = "docs"
SOURCES_SUBDIR = "sources"
CHUNKS_SUBDIR = "chunks"
CHUNKS_EXTRACTED_SUBDIR = "extracted"
CHUNKS_MANUAL_SUBDIR = "manual"

MANUAL_REQUIRED_COLUMNS = frozenset({"chunk_id", "chunk_string", "evidence"})
MANUAL_SKIP_METADATA = frozenset({"chunk_string", "evidence", "source"})

# Upper bound for chunk size (S2 token cap; pypdf fallback approximates via chars).
MAX_CHUNK_TOKENS = 300
_CHARS_PER_TOKEN_ESTIMATE = 4
_FALLBACK_MAX_CHARS = MAX_CHUNK_TOKENS * _CHARS_PER_TOKEN_ESTIMATE
_FALLBACK_MIN_CHARS = 80


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def default_kb_dir(repo_root_path: Path | None = None) -> Path:
    """Default knowledge-base root: ``Knowledge Base/Red Flags``."""
    return (repo_root_path or repo_root()) / "Knowledge Base" / "Red Flags"


def kb_slug(kb_dir: Path) -> str:
    """Stable slug from the knowledge-base folder name (e.g. ``Red Flags`` -> ``red_flags``)."""
    slug = re.sub(r"[^a-z0-9]+", "_", kb_dir.name.lower()).strip("_")
    return slug or "kb"


def extracted_registry_filename(kb_dir: Path) -> str:
    return f"{kb_slug(kb_dir)}_extracted.csv"


def manual_registry_filename(kb_dir: Path) -> str:
    return f"{kb_slug(kb_dir)}_manual.csv"


def resolve_extracted_chunks_csv(
    kb_dir: Path,
    *,
    chunks_registry_name: str | None = None,
) -> Path:
    """Default: ``<kb_dir>/chunks/extracted/<slug>_extracted.csv``."""
    root = kb_dir.resolve()
    name = chunks_registry_name or extracted_registry_filename(root)
    return root / CHUNKS_SUBDIR / CHUNKS_EXTRACTED_SUBDIR / name


def resolve_manual_chunks_csv(
    kb_dir: Path,
    *,
    chunks_registry_name: str | None = None,
) -> Path:
    """Default: ``<kb_dir>/chunks/manual/<slug>_manual.csv``."""
    root = kb_dir.resolve()
    name = chunks_registry_name or manual_registry_filename(root)
    return root / CHUNKS_SUBDIR / CHUNKS_MANUAL_SUBDIR / name


def resolve_kb_paths(
    kb_dir: Path,
    *,
    chunks_registry_name: str | None = None,
    registry: RegistryFormat = "extracted",
) -> tuple[Path, Path, Path]:
    """
    Resolve ``(docs_dir, sources_dir, chunks_csv)`` under a knowledge-base root.

    ``registry`` selects the default chunks CSV under ``chunks/extracted/`` or
    ``chunks/manual/`` when ``chunks_registry_name`` is not set.
    """
    root = kb_dir.resolve()
    docs = root / DOCS_SUBDIR
    sources = root / SOURCES_SUBDIR
    if chunks_registry_name:
        chunks_csv = root / CHUNKS_SUBDIR / chunks_registry_name
    elif registry == "manual":
        chunks_csv = resolve_manual_chunks_csv(root)
    else:
        chunks_csv = resolve_extracted_chunks_csv(root)
    return docs, sources, chunks_csv


def detect_registry_format(fieldnames: list[str] | None) -> RegistryFormat:
    """Infer CSV registry type from header columns."""
    cols = {(h or "").strip() for h in (fieldnames or []) if h}
    if "metadata_tags" in cols:
        return "extracted"
    if MANUAL_REQUIRED_COLUMNS <= cols:
        return "manual"
    raise ValueError(
        "Unrecognized chunk registry columns. "
        f"Need manual {sorted(MANUAL_REQUIRED_COLUMNS)} or extracted "
        f"{list(CSV_FIELDNAMES)}; got {sorted(cols)}"
    )


def _open_registry_encoding(chunks_csv: Path) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp1252"):
        try:
            with chunks_csv.open(encoding=encoding) as probe:
                probe.read()
            return encoding
        except UnicodeDecodeError:
            continue
    return "utf-8-sig"


def validate_kb_layout(kb_dir: Path) -> None:
    """Require ``docs/`` and ``sources/`` under the knowledge-base root."""
    docs, sources, _ = resolve_kb_paths(kb_dir)
    missing: list[str] = []
    if not docs.is_dir():
        missing.append(f"{DOCS_SUBDIR}/ ({docs})")
    if not sources.is_dir():
        missing.append(f"{SOURCES_SUBDIR}/ ({sources})")
    if missing:
        raise FileNotFoundError(
            f"Knowledge-base folder {kb_dir.resolve()} must contain: "
            + ", ".join(missing)
        )


def resolve_run_paths(
    kb_dir: Path,
    *,
    docs_dir: Path | None = None,
    sources_dir: Path | None = None,
    chunks_csv: Path | None = None,
    chunks_registry_name: str | None = None,
) -> tuple[Path, Path, Path]:
    """Merge explicit path overrides with paths derived from ``kb_dir``."""
    base_docs, base_sources, base_chunks = resolve_kb_paths(
        kb_dir, chunks_registry_name=chunks_registry_name
    )
    return (
        (docs_dir or base_docs).resolve(),
        (sources_dir or base_sources).resolve(),
        (chunks_csv or base_chunks).resolve(),
    )


# Backward-compatible aliases
def red_flags_kb_dir(repo_root_path: Path | None = None) -> Path:
    return default_kb_dir(repo_root_path)


def default_red_flags_paths(
    repo_root_path: Path | None = None,
) -> tuple[Path, Path, Path]:
    return resolve_kb_paths(default_kb_dir(repo_root_path))


def load_sources_table(sources_dir: Path) -> dict[str, dict[str, str]]:
    """Map source_id -> row dict (header keys lowercased)."""
    csv_files = sorted(sources_dir.glob("*.csv"))
    xlsx_files = sorted(sources_dir.glob("*.xlsx"))
    if csv_files:
        return _load_sources_csv(csv_files[0])
    if xlsx_files:
        return _load_sources_xlsx(xlsx_files[0])
    raise FileNotFoundError(
        f"No sources catalog in {sources_dir} (expected *.csv or *.xlsx)."
    )


def _load_sources_csv(path: Path) -> dict[str, dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise ValueError(f"Empty CSV: {path}")
        rows: dict[str, dict[str, str]] = {}
        for raw in reader:
            row = {_normalize_key(k): (v or "").strip() for k, v in raw.items()}
            sid = row.get("source_id") or row.get("id") or ""
            if not sid:
                continue
            rows[sid] = row
        return rows


def _normalize_key(key: str | None) -> str:
    return (key or "").strip().lower().replace(" ", "_")


def _load_sources_xlsx(path: Path) -> dict[str, dict[str, str]]:
    """Read first worksheet via stdlib (no openpyxl)."""
    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with zipfile.ZipFile(path) as z:
        shared_strings: list[str] = []
        if "xl/sharedStrings.xml" in z.namelist():
            root = ET.fromstring(z.read("xl/sharedStrings.xml"))
            for si in root.findall("m:si", ns):
                parts = [t.text or "" for t in si.findall(".//m:t", ns)]
                shared_strings.append("".join(parts))
        sheet = ET.fromstring(z.read("xl/worksheets/sheet1.xml"))
        grid: list[list[str]] = []
        for row_el in sheet.findall(".//m:row", ns):
            row_cells: list[str] = []
            for cell in row_el.findall("m:c", ns):
                v = cell.find("m:v", ns)
                if v is None or v.text is None:
                    row_cells.append("")
                elif cell.get("t") == "s":
                    row_cells.append(shared_strings[int(v.text)])
                else:
                    row_cells.append(v.text)
            grid.append(row_cells)
    if not grid:
        raise ValueError(f"No rows in {path}")
    headers = [_normalize_key(h) for h in grid[0]]
    out: dict[str, dict[str, str]] = {}
    for line in grid[1:]:
        if not any(line):
            continue
        padded = line + [""] * (len(headers) - len(line))
        row = dict(zip(headers, (c.strip() for c in padded)))
        sid = row.get("source_id") or row.get("id") or ""
        if sid:
            out[sid] = row
    return out


def format_source_citation(row: dict[str, str]) -> str:
    """Single retrieval-friendly source string from catalog fields."""
    parts: list[str] = []
    for key in ("title", "author", "year", "authority", "doi"):
        val = row.get(key, "").strip()
        if val:
            parts.append(f"{key}: {val}")
    return " | ".join(parts) if parts else row.get("source_id", "unknown")


def brief_source_citation(source: str) -> str:
    """Author and publication year from a :func:`format_source_citation` string."""
    author = ""
    year = ""
    for part in source.split("|"):
        part = part.strip()
        low = part.lower()
        if low.startswith("author:"):
            author = part.split(":", 1)[1].strip()
        elif low.startswith("year:"):
            year = part.split(":", 1)[1].strip()
    if author and year:
        return f"{author} ({year})"
    if author:
        return author
    if year:
        return year
    trimmed = source.strip()
    if len(trimmed) > 120:
        return trimmed[:117] + "..."
    return trimmed or "unknown"


def enrich_chunk_registry_evidence(
    *,
    chunks_csv: Path,
    sources_dir: Path,
    source_column: str = "source",
    evidence_column: str = "evidence",
    evidence_level_column: str = "evidence_level",
) -> int:
    """
    Fill ``evidence`` and ``evidence_level`` on a chunk registry CSV from the sources catalog.

    Rows are matched on ``source_column`` (e.g. ``source``) to ``source_id`` in
    ``sources_dir`` (first ``*.csv`` or ``*.xlsx``). Citation text uses
    :func:`format_source_citation` (title, author, year, authority, doi).
    """
    chunks_csv = chunks_csv.resolve()
    sources = load_sources_table(sources_dir.resolve())

    read_enc = "utf-8-sig"
    for encoding in ("utf-8-sig", "utf-8", "cp1252"):
        try:
            with chunks_csv.open(encoding=encoding) as probe:
                probe.read()
            read_enc = encoding
            break
        except UnicodeDecodeError:
            continue

    with chunks_csv.open(newline="", encoding=read_enc) as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise ValueError(f"Empty chunk registry: {chunks_csv}")
        fieldnames = list(reader.fieldnames)
        for col in (evidence_column, evidence_level_column):
            if col not in fieldnames:
                raise ValueError(
                    f"Chunk registry {chunks_csv} missing column: {col}"
                )
        if source_column not in fieldnames:
            raise ValueError(
                f"Chunk registry {chunks_csv} missing column: {source_column}"
            )
        rows: list[dict[str, str]] = []
        missing_sources: set[str] = set()
        updated = 0
        for raw in reader:
            row = {k: (raw.get(k) or "").strip() for k in fieldnames}
            sid = row.get(source_column, "").strip()
            if not sid:
                rows.append(row)
                continue
            catalog = sources.get(sid)
            if catalog is None:
                missing_sources.add(sid)
                rows.append(row)
                continue
            citation = format_source_citation(catalog)
            level = catalog.get("evidence_level", "").strip()
            if row.get(evidence_column) != citation or row.get(evidence_level_column) != level:
                updated += 1
            row[evidence_column] = citation
            row[evidence_level_column] = level
            rows.append(row)

    with chunks_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, quoting=csv.QUOTE_MINIMAL)
        writer.writeheader()
        writer.writerows(rows)

    if missing_sources:
        _log.warning(
            "No sources catalog entry for source id(s): %s",
            ", ".join(sorted(missing_sources)),
        )
    _log.info(
        "Wrote %s (%d row(s), %d evidence field(s) updated)",
        chunks_csv,
        len(rows),
        updated,
    )
    return 1 if missing_sources else 0


def format_metadata_tags(
    *,
    source_id: str,
    doc_name: str,
    chunk_index: int,
    method: str,
    corpus: str = "red_flags",
    extra: dict[str, str] | None = None,
) -> str:
    tags = {
        "corpus": corpus,
        "source_id": source_id,
        "doc": doc_name,
        "chunk_index": str(chunk_index),
        "chunk_method": method,
    }
    if extra:
        tags.update(extra)
    return ";".join(f"{k}={v}" for k, v in tags.items())


def parse_metadata_tags(tag_str: str) -> dict[str, str]:
    meta: dict[str, str] = {}
    for piece in tag_str.split(";"):
        piece = piece.strip()
        if not piece or "=" not in piece:
            continue
        k, _, v = piece.partition("=")
        meta[k.strip()] = v.strip()
    return meta


def list_doc_pdfs(docs_dir: Path) -> list[Path]:
    pdfs = [p for p in docs_dir.glob("*.pdf") if p.is_file()]

    def sort_key(p: Path) -> tuple[int, str]:
        stem = p.stem
        if stem.isdigit():
            return (int(stem), stem)
        return (10**9, stem)

    return sorted(pdfs, key=sort_key)


def _normalize_chunk_text(text: str) -> str:
    text = text.replace("\r\n", "\n").strip()
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def _chunk_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _nodes_to_plain_text(nodes: list[dict[str, Any]]) -> str:
    ordered = sorted(nodes, key=lambda n: n.get("reading_order", 999))
    parts: list[str] = []
    for node in ordered:
        t = (node.get("text") or "").strip()
        label = (node.get("label") or "").strip()
        if not t or t == label:
            continue
        parts.append(t)
    return _normalize_chunk_text("\n\n".join(parts))


def _pdf_to_page_images(pdf_path: Path, out_dir: Path, dpi: int = 150) -> list[Path]:
    import fitz  # pymupdf

    doc = fitz.open(pdf_path)
    paths: list[Path] = []
    try:
        for i in range(len(doc)):
            page = doc.load_page(i)
            pix = page.get_pixmap(dpi=dpi)
            img_path = out_dir / f"page_{i + 1:04d}.png"
            pix.save(str(img_path))
            paths.append(img_path)
    finally:
        doc.close()
    return paths


def _chunk_pdf_with_s2(
    pdf_path: Path,
    *,
    max_token_length: int,
    extract_text: bool,
) -> list[str] | None:
    try:
        from s2chunking import StructuralSemanticChunker
    except ImportError:
        _log.debug("s2chunking not installed; skipping S2 path")
        return None

    with tempfile.TemporaryDirectory(prefix="s2_pages_") as tmp:
        tmp_path = Path(tmp)
        try:
            image_paths = _pdf_to_page_images(pdf_path, tmp_path)
        except ImportError:
            _log.warning("pymupdf (fitz) required for S2 PDF rendering; pip install pymupdf")
            return None
        if not image_paths:
            return None

        chunker = StructuralSemanticChunker(max_token_length=max_token_length)
        clusters, nodes = chunker.chunk_from_images(
            [str(p) for p in image_paths],
            extract_text=extract_text,
        )
        if not clusters or not nodes:
            _log.warning("S2 returned no clusters for %s", pdf_path.name)
            return None

        by_cluster: dict[int, list[dict[str, Any]]] = {}
        for node_id, cluster_id in clusters.items():
            node = next((n for n in nodes if n["global_id"] == node_id), None)
            if node:
                by_cluster.setdefault(cluster_id, []).append(node)

        texts: list[str] = []
        for cluster_id in sorted(by_cluster):
            plain = _nodes_to_plain_text(by_cluster[cluster_id])
            if len(plain) >= _FALLBACK_MIN_CHARS:
                texts.append(plain)
        return texts if texts else None


def _extract_pdf_text(pdf_path: Path) -> str:
    from pypdf import PdfReader

    reader = PdfReader(str(pdf_path))
    pages = []
    for page in reader.pages:
        pages.append(page.extract_text() or "")
    return "\n\n".join(pages)


def _split_text_to_max_chars(text: str, max_chars: int) -> list[str]:
    """Split text into segments of at most ``max_chars`` (word boundaries)."""
    text = _normalize_chunk_text(text)
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]
    words = text.split()
    segments: list[str] = []
    cur: list[str] = []
    cur_len = 0
    for w in words:
        wlen = len(w)
        if cur and cur_len + wlen + 1 > max_chars:
            segments.append(_normalize_chunk_text(" ".join(cur)))
            cur = []
            cur_len = 0
        cur.append(w)
        cur_len += wlen + (1 if cur_len else 0)
    if cur:
        segments.append(_normalize_chunk_text(" ".join(cur)))
    return segments


def _chunk_text_fallback(full_text: str, *, max_chars: int) -> list[str]:
    full_text = _normalize_chunk_text(full_text)
    if not full_text:
        return []
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n+", full_text) if p.strip()]
    if not paragraphs:
        paragraphs = [full_text]

    chunks: list[str] = []
    buf: list[str] = []
    size = 0
    for para in paragraphs:
        if len(para) > max_chars:
            if buf:
                chunks.append(_normalize_chunk_text("\n\n".join(buf)))
                buf = []
                size = 0
            chunks.extend(_split_text_to_max_chars(para, max_chars))
            continue
        plen = len(para)
        if buf and size + plen + 2 > max_chars:
            chunks.append(_normalize_chunk_text("\n\n".join(buf)))
            buf = []
            size = 0
        buf.append(para)
        size += plen + 2
    if buf:
        joined = _normalize_chunk_text("\n\n".join(buf))
        if len(joined) > max_chars:
            chunks.extend(_split_text_to_max_chars(joined, max_chars))
        else:
            chunks.append(joined)

    bounded: list[str] = []
    for c in chunks:
        if len(c) <= max_chars:
            bounded.append(c)
        else:
            bounded.extend(_split_text_to_max_chars(c, max_chars))

    return [c for c in bounded if len(c) >= _FALLBACK_MIN_CHARS]


def chunk_document(
    pdf_path: Path,
    *,
    max_token_length: int = MAX_CHUNK_TOKENS,
    s2_extract_text: bool = True,
    fallback_max_chars: int = _FALLBACK_MAX_CHARS,
) -> tuple[list[str], str]:
    """Return (chunk texts, method name)."""
    s2_texts = _chunk_pdf_with_s2(
        pdf_path,
        max_token_length=max_token_length,
        extract_text=s2_extract_text,
    )
    if s2_texts:
        return s2_texts, "s2"

    _log.info("Using pypdf paragraph fallback for %s", pdf_path.name)
    return (
        _chunk_text_fallback(_extract_pdf_text(pdf_path), max_chars=fallback_max_chars),
        "pypdf",
    )


def write_chunks_csv(rows: list[dict[str, str]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=CSV_FIELDNAMES,
            quoting=csv.QUOTE_MINIMAL,
        )
        writer.writeheader()
        writer.writerows(rows)


def load_chunks_registry(chunks_csv: Path) -> list[dict[str, str]]:
    """Load rows from a chunk registry CSV written by :func:`write_chunks_csv`."""
    if not chunks_csv.is_file():
        raise FileNotFoundError(f"Chunk registry not found: {chunks_csv}")
    with chunks_csv.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise ValueError(f"Empty chunk registry: {chunks_csv}")
        missing = set(CSV_FIELDNAMES) - set(reader.fieldnames)
        if missing:
            raise ValueError(
                f"Chunk registry {chunks_csv} missing columns: {sorted(missing)}"
            )
        rows: list[dict[str, str]] = []
        for raw in reader:
            row = {k: (raw.get(k) or "").strip() for k in CSV_FIELDNAMES}
            if not row["chunk_id"] or not row["chunk_string"]:
                _log.warning("Skipping row with empty chunk_id or chunk_string")
                continue
            rows.append(row)
        return rows


def _ingest_extracted_rows(
    *,
    sub_collection: str,
    chunks_csv: Path,
    rows: list[dict[str, str]],
) -> int:
    from app.services.rag import ingest_evidence_chunk

    for row in rows:
        ingest_evidence_chunk(
            row["chunk_id"],
            row["chunk_string"],
            sub_collection=sub_collection,
            source=row["source"],
            metadatas=parse_metadata_tags(row["metadata_tags"]),
        )
    _log.info(
        "Ingested %d extracted chunk(s) from %s into %r",
        len(rows),
        chunks_csv,
        sub_collection,
    )
    return 0


def _ingest_manual_rows(
    *,
    sub_collection: str,
    chunks_csv: Path,
) -> int:
    from app.services.rag import ingest_evidence_chunk
    from app.services.rag.store import validate_sub_collection

    canonical = validate_sub_collection(sub_collection)
    read_enc = _open_registry_encoding(chunks_csv)
    ingested = 0

    with chunks_csv.open(newline="", encoding=read_enc) as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise ValueError(f"Empty chunk registry: {chunks_csv}")
        missing = MANUAL_REQUIRED_COLUMNS - {
            h.strip() for h in reader.fieldnames if h
        }
        if missing:
            raise ValueError(
                f"Manual registry {chunks_csv} missing columns: {sorted(missing)}"
            )
        for raw in reader:
            row = {
                (k or "").strip(): (raw.get(k) or "").strip()
                for k in reader.fieldnames
                if k
            }
            chunk_id = row.get("chunk_id", "")
            text = row.get("chunk_string", "")
            source = row.get("evidence", "")
            if not chunk_id or not text:
                _log.warning(
                    "Skipping row with empty chunk_id or chunk_string in %s",
                    chunks_csv,
                )
                continue
            if not source:
                _log.warning(
                    "Skipping chunk %s: empty evidence (source) in %s",
                    chunk_id,
                    chunks_csv,
                )
                continue
            metadatas = {
                key: val
                for key, val in row.items()
                if key not in MANUAL_SKIP_METADATA and val
            }
            ingest_evidence_chunk(
                chunk_id,
                text,
                sub_collection=canonical,
                source=source,
                metadatas=metadatas or None,
            )
            ingested += 1

    if ingested == 0:
        _log.error("No ingestible manual rows in %s", chunks_csv)
        return 2
    _log.info(
        "Ingested %d manual chunk(s) from %s into %r",
        ingested,
        chunks_csv,
        canonical,
    )
    return 0


def ingest_chunks_from_csv(
    *,
    sub_collection: str,
    chunks_csv: Path,
    registry_format: RegistryFormat = "auto",
) -> int:
    """
    Upsert rows from a reviewed chunk registry CSV into a Chroma sub-collection.

    ``registry_format`` may be ``extracted`` (PDF pipeline CSV), ``manual`` (curated
    registry with ``evidence`` column), or ``auto`` (detect from headers).
    """
    chunks_csv = chunks_csv.resolve()
    if not chunks_csv.is_file():
        raise FileNotFoundError(f"Chunk registry not found: {chunks_csv}")

    read_enc = _open_registry_encoding(chunks_csv)
    with chunks_csv.open(newline="", encoding=read_enc) as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        fmt = (
            detect_registry_format(fieldnames)
            if registry_format == "auto"
            else registry_format
        )

    if fmt == "extracted":
        rows = load_chunks_registry(chunks_csv)
        if not rows:
            _log.error("No ingestible rows in %s", chunks_csv)
            return 2
        return _ingest_extracted_rows(
            sub_collection=sub_collection,
            chunks_csv=chunks_csv,
            rows=rows,
        )
    return _ingest_manual_rows(
        sub_collection=sub_collection,
        chunks_csv=chunks_csv,
    )


def ingest_chunks_from_registry(
    *,
    sub_collection: str,
    kb_dir: Path | None = None,
    chunks_csv: Path | None = None,
    chunks_registry_name: str | None = None,
    registry_format: RegistryFormat = "extracted",
) -> int:
    """
    Upsert a chunk registry CSV into Chroma (backward-compatible wrapper).

    Resolves ``chunks_csv`` from ``kb_dir`` using ``registry_format`` when the path
    is omitted (default: ``chunks/extracted/<slug>_extracted.csv``).
    """
    if chunks_csv is None:
        if kb_dir is None:
            raise ValueError("ingest_chunks_from_registry requires kb_dir or chunks_csv")
        reg = registry_format if registry_format != "auto" else "extracted"
        _, _, chunks_csv = resolve_kb_paths(
            kb_dir,
            chunks_registry_name=chunks_registry_name,
            registry=reg,
        )
    return ingest_chunks_from_csv(
        sub_collection=sub_collection,
        chunks_csv=chunks_csv,
        registry_format=registry_format,
    )


def run_chunk_catalog(
    *,
    kb_dir: Path,
    docs_dir: Path | None = None,
    sources_dir: Path | None = None,
    chunks_csv: Path | None = None,
    chunks_registry_name: str | None = None,
    max_token_length: int = MAX_CHUNK_TOKENS,
    s2_extract_text: bool = True,
    fallback_max_chars: int = _FALLBACK_MAX_CHARS,
    chunk_id_prefix: str | None = None,
    corpus: str | None = None,
) -> int:
    """
    Chunk PDFs under a knowledge-base root and write the registry CSV (no vector ingest).

    ``kb_dir`` must contain ``docs/`` and ``sources/`` (same layout as Red Flags).
    """
    validate_kb_layout(kb_dir)
    if chunks_csv is None and chunks_registry_name is None:
        chunks_csv = resolve_extracted_chunks_csv(kb_dir)
    docs_dir, sources_dir, chunks_csv = resolve_run_paths(
        kb_dir,
        docs_dir=docs_dir,
        sources_dir=sources_dir,
        chunks_csv=chunks_csv,
        chunks_registry_name=chunks_registry_name,
    )
    slug = kb_slug(kb_dir)
    id_prefix = chunk_id_prefix or slug
    corpus_tag = corpus or slug

    sources = load_sources_table(sources_dir)
    pdfs = list_doc_pdfs(docs_dir)
    if not pdfs:
        _log.error("No PDFs in %s", docs_dir)
        return 1

    csv_rows: list[dict[str, str]] = []
    seen_hashes: set[str] = set()

    for pdf_path in pdfs:
        source_id = pdf_path.stem
        if source_id not in sources:
            _log.warning("No source row for doc %s; skipping", pdf_path.name)
            continue
        source_row = sources[source_id]
        citation = format_source_citation(source_row)
        texts, method = chunk_document(
            pdf_path,
            max_token_length=max_token_length,
            s2_extract_text=s2_extract_text,
            fallback_max_chars=fallback_max_chars,
        )
        if not texts:
            _log.warning("No chunks produced for %s", pdf_path.name)
            continue

        local_idx = 0
        for text in texts:
            h = _chunk_hash(text)
            if h in seen_hashes:
                _log.debug("Skipping duplicate chunk hash for %s", pdf_path.name)
                continue
            seen_hashes.add(h)
            local_idx += 1
            chunk_id = f"{id_prefix}_{source_id}_{local_idx:04d}"
            meta_tags = format_metadata_tags(
                source_id=source_id,
                doc_name=pdf_path.name,
                chunk_index=local_idx,
                method=method,
                corpus=corpus_tag,
            )
            csv_rows.append(
                {
                    "chunk_id": chunk_id,
                    "chunk_string": text,
                    "source": citation,
                    "metadata_tags": meta_tags,
                }
            )

        _log.info(
            "Processed %s: %d unique chunks (%s)",
            pdf_path.name,
            local_idx,
            method,
        )

    write_chunks_csv(csv_rows, chunks_csv)
    _log.info(
        "Wrote %d rows to %s (review, then scripts/ingest_chunks.py)",
        len(csv_rows),
        chunks_csv,
    )
    return 0 if csv_rows else 2


# Backward-compatible alias
run_chunk_and_ingest = run_chunk_catalog
