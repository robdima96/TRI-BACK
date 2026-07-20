"""Compare RAG embedding models on red-flag chunks + vignette queries.

For each **local** encoder directory: build a temporary Chroma collection (cosine),
ingest all red-flag manual chunks, embed full patient queries (column B), retrieve
top-k (default ``settings.rag_top_k`` from ``app/config.py``), and write per-model
reports into the embeddings test CSV (columns G–I).

Models are loaded with ``local_files_only=True``; Hugging Face Hub downloads are
disabled (``HF_HUB_OFFLINE`` / ``TRANSFORMERS_OFFLINE``).

Run from repo root::

    python "Embeddings test/compare_embedding_models.py"

    python "Embeddings test/compare_embedding_models.py" --dry-run
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_DEFAULT_CHUNKS = (
    _ROOT / "Knowledge Base" / "Red Flags" / "chunks" / "manual" / "red_flags_manual.csv"
)
_DEFAULT_RESULTS_CSV = (
    _ROOT
    / "tests"
    / "data"
    / "results"
    / "NER_checklist_matching_with_vignettes_embeddings_test.csv"
)

_COLLECTION_METADATA = {"hnsw:space": "cosine"}

_MODELS: tuple[tuple[str, str, str], ...] = (
    ("Clinical_sBERT", r"E:\DigiMSKbot\Clinical_sBERT", "Clinical_sBERT"),
    ("GliNER", r"E:\DigiMSKbot\GliNER-BioMed", "GliNER"),
    ("Bio_ClinicalBERT", r"E:\DigiMSKbot\Bio_ClinicalBERT", "Bio_ClinicalBERT"),
    ("gatortron-base", r"E:\DigiMSKbot\gatortron-base", "gatortron-base"),
)


def _distance_to_score(d: float) -> float:
    return max(0.0, min(1.0, 1.0 / (1.0 + max(0.0, d))))


def _cosine_similarity_from_distance(d: float) -> float:
    """Chroma cosine space: distance = 1 - cosine_similarity (L2-normalized vectors)."""
    return max(0.0, min(1.0, 1.0 - float(d)))


def _force_hf_offline() -> None:
    """Prevent Hugging Face Hub network access during benchmark runs."""
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")


def _subdir_with_hf_config(root: Path) -> Path | None:
    for name in ("encoder", "backbone", "baseline", "deberta"):
        p = root / name
        if p.is_dir() and (p / "config.json").is_file():
            return p
    return None


def _is_hf_model_dir(path: Path) -> bool:
    return path.is_dir() and (path / "config.json").is_file()


def _is_gliner_bundle(root: Path) -> bool:
    """GliNER-BioMed layout: ``gliner_config.json`` + checkpoint at bundle root."""
    if not (root / "gliner_config.json").is_file():
        return False
    return any(
        (root / name).is_file()
        for name in (
            "pytorch_model.bin",
            "model.safetensors",
            "pytorch_model.safetensors",
        )
    )


def _read_gliner_config(root: Path) -> dict[str, Any]:
    gl = root / "gliner_config.json"
    try:
        with gl.open(encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _gliner_backbone_model_id(root: Path) -> str | None:
    gc = _read_gliner_config(root)
    raw = gc.get("model_name") or gc.get("encoder_model_name")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    enc = gc.get("encoder_config")
    if isinstance(enc, dict):
        raw = enc.get("_name_or_path")
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    return None


def _hub_model_cached_snapshot_dir(model_id: str) -> str | None:
    """Local HF Hub cache snapshot for ``model_id`` (no network; ``local_files_only``)."""
    if not model_id.strip():
        return None
    try:
        from huggingface_hub import hf_hub_download

        config_path = hf_hub_download(
            model_id.strip(),
            "config.json",
            local_files_only=True,
        )
        return str(Path(config_path).parent.resolve())
    except Exception:
        return None


def _local_encoder_pretrained_paths(encoder_dir: str) -> list[str]:
    """Absolute paths to on-disk HF encoder layouts (no Hub download)."""
    root = Path(encoder_dir)
    if not root.is_dir():
        return []
    candidates: list[Path] = []
    if _is_hf_model_dir(root):
        candidates.append(root)
    else:
        nested = _subdir_with_hf_config(root)
        if nested is not None:
            candidates.append(nested)
        for name in ("encoder", "backbone", "baseline", "deberta"):
            p = root / name
            if _is_hf_model_dir(p):
                candidates.append(p)
        if _is_gliner_bundle(root):
            backbone_id = _gliner_backbone_model_id(root)
            if backbone_id:
                explicit = Path(backbone_id)
                if _is_hf_model_dir(explicit):
                    candidates.append(explicit)
                else:
                    for rel in (
                        backbone_id,
                        Path(backbone_id.replace("\\", "/")).name,
                    ):
                        rel_path = root / rel
                        if _is_hf_model_dir(rel_path):
                            candidates.append(rel_path)
                    cached = _hub_model_cached_snapshot_dir(backbone_id)
                    if cached:
                        candidates.append(Path(cached))
    out: list[str] = []
    seen: set[str] = set()
    for path in candidates:
        key = str(path.resolve())
        if key not in seen:
            seen.add(key)
            out.append(key)
    return out


def _resolved_encoder_sources(encoder_dir: str) -> list[tuple[str, bool]]:
    """``(pretrained_path, local_files_only)`` — local paths only, no Hub fallback."""
    return [(p, True) for p in _local_encoder_pretrained_paths(encoder_dir)]


def _encoder_path_looks_valid(encoder_dir: str) -> bool:
    root = Path(encoder_dir)
    if _local_encoder_pretrained_paths(encoder_dir):
        return True
    if _is_gliner_bundle(root):
        backbone_id = _gliner_backbone_model_id(root)
        if backbone_id and _hub_model_cached_snapshot_dir(backbone_id):
            return True
        # Bundle present; load() will surface a clear error if backbone cache is missing.
        return True
    return False


@dataclass(frozen=True)
class ChunkRow:
    chunk_id: str
    chunk_string: str


@dataclass(frozen=True)
class RetrievalHit:
    chunk_id: str
    distance: float
    cosine_similarity: float
    norm_score: float
    text: str


class SentenceTransformerBackend:
    """``sentence_transformers`` encoder (production Clinical_sBERT path)."""

    def __init__(self, model_dir: str) -> None:
        self.encoder_dir = model_dir
        self._model: Any = None
        self.embedding_dim: int | None = None

    def load(self) -> None:
        _force_hf_offline()
        from sentence_transformers import SentenceTransformer

        path = Path(self.encoder_dir)
        if not path.is_dir() or not (path / "config.json").is_file():
            raise FileNotFoundError(
                f"Not a local sentence-transformers folder: {self.encoder_dir!r}"
            )
        self._model = SentenceTransformer(str(path.resolve()), local_files_only=True)
        probe = self._model.encode("probe", normalize_embeddings=True)
        self.embedding_dim = int(len(probe))

    def unload(self) -> None:
        self._model = None
        self.embedding_dim = None

    def embed(self, text: str) -> list[float]:
        if not (text and str(text).strip()):
            return []
        if self._model is None:
            raise RuntimeError("SentenceTransformerBackend.load() was not called")
        vec = self._model.encode(text, normalize_embeddings=True)
        return list(vec.astype(float))


class EmbeddingBackend:
    """Mean-pooled HF encoder for one model directory (isolated from app globals)."""

    def __init__(self, encoder_dir: str, *, max_length: int = 256) -> None:
        self.encoder_dir = encoder_dir
        self.max_length = max_length
        self._tok: Any = None
        self._mdl: Any = None
        self._device: Any = None
        self.embedding_dim: int | None = None

    def load(self) -> None:
        _force_hf_offline()
        sources = _resolved_encoder_sources(self.encoder_dir)
        if not sources:
            root = Path(self.encoder_dir)
            hint = (
                "expected config.json, encoder/ or deberta/ subdir, or a cached "
                "Hugging Face snapshot for the backbone named in gliner_config.json "
                "(e.g. microsoft/deberta-v3-small under ~/.cache/huggingface/hub)"
            )
            if _is_gliner_bundle(root):
                bid = _gliner_backbone_model_id(root) or "(unknown)"
                hint = (
                    f"GliNER bundle found at {self.encoder_dir!r} but no local backbone "
                    f"for {bid!r}. {hint}"
                )
            raise FileNotFoundError(f"No local encoder weights under {self.encoder_dir!r}. {hint}")
        from transformers import AutoConfig, AutoModel, AutoTokenizer
        import torch

        last_err: Exception | None = None
        for pretrained, _local_only in sources:
            try:
                cfg = AutoConfig.from_pretrained(pretrained, local_files_only=True)
                self.embedding_dim = int(getattr(cfg, "hidden_size", 0) or 0)
                self._tok = AutoTokenizer.from_pretrained(
                    pretrained, local_files_only=True
                )
                self._mdl = AutoModel.from_pretrained(
                    pretrained, local_files_only=True
                )
                self._mdl.eval()
                self._device = torch.device(
                    "cuda" if torch.cuda.is_available() else "cpu"
                )
                self._mdl.to(self._device)
                return
            except Exception as e:
                last_err = e
        raise RuntimeError(
            f"Failed to load encoder from {self.encoder_dir!r}: {last_err}"
        )

    def unload(self) -> None:
        self._tok = None
        self._mdl = None
        self._device = None
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass

    @staticmethod
    def _mean_pool(last_hidden: Any, attention_mask: Any) -> Any:
        import torch

        mask = attention_mask.unsqueeze(-1).float()
        summed = (last_hidden * mask).sum(dim=1)
        counts = mask.sum(dim=1).clamp(min=1e-9)
        return summed / counts

    def embed(self, text: str) -> list[float]:
        if not (text and str(text).strip()):
            return []
        if self._tok is None or self._mdl is None or self._device is None:
            raise RuntimeError("EmbeddingBackend.load() was not called")
        import torch

        enc = self._tok(
            text,
            return_tensors="pt",
            truncation=True,
            max_length=self.max_length,
            padding=True,
        )
        enc = {k: v.to(self._device) for k, v in enc.items()}
        with torch.no_grad():
            out = self._mdl(**enc)
            pooled = self._mean_pool(out.last_hidden_state, enc["attention_mask"])
            return list(pooled[0].float().cpu().tolist())


def _load_red_flag_chunks(path: Path) -> list[ChunkRow]:
    rows: list[ChunkRow] = []
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            cid = (row.get("chunk_id") or "").strip()
            text = (row.get("chunk_string") or "").strip()
            if cid and text:
                rows.append(ChunkRow(chunk_id=cid, chunk_string=text))
    if not rows:
        raise ValueError(f"No chunks loaded from {path}")
    return rows


def _read_results_csv(path: Path) -> tuple[list[str], list[list[str]]]:
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        all_rows = list(reader)
    if not all_rows:
        raise ValueError(f"Empty CSV: {path}")
    header = [h.lstrip("\ufeff") for h in all_rows[0]]
    data = all_rows[1:]
    return header, data


def _write_results_csv(path: Path, header: list[str], data: list[list[str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(data)


def _pad_row(row: list[str], ncols: int) -> list[str]:
    out = list(row)
    while len(out) < ncols:
        out.append("")
    return out[:ncols]


def _query_collection(
    coll: Any,
    query_embedding: list[float],
    *,
    top_k: int,
) -> list[RetrievalHit]:
    count = coll.count()
    if count == 0:
        return []
    n_results = min(top_k, max(1, count))
    res = coll.query(
        query_embeddings=[query_embedding],
        n_results=n_results,
        include=["distances", "documents"],
    )
    ids0 = res["ids"][0] if res.get("ids") else []
    dists0 = res["distances"][0] if res.get("distances") else [0.0] * len(ids0)
    docs0 = res["documents"][0] if res.get("documents") else [""] * len(ids0)
    hits: list[RetrievalHit] = []
    for chunk_id, d, doc in zip(ids0, dists0, docs0):
        dist = float(d)
        hits.append(
            RetrievalHit(
                chunk_id=str(chunk_id),
                distance=dist,
                cosine_similarity=_cosine_similarity_from_distance(dist),
                norm_score=_distance_to_score(dist),
                text=doc if doc is not None else "",
            )
        )
    hits.sort(key=lambda h: h.norm_score, reverse=True)
    return hits[:top_k]


def _format_report(
    *,
    model_name: str,
    encoder_dir: str,
    query: str,
    top_k: int,
    chroma_path: str,
    chunk_count: int,
    embedding_dim: int,
    hits: list[RetrievalHit],
) -> str:
    lines: list[str] = [
        f"model: {model_name}",
        f"encoder_dir: {encoder_dir}",
        f"embedding_dim: {embedding_dim}",
        f"query: {query!r}",
        f"top_k: {top_k}",
        f"chroma_path: {chroma_path}",
        f"indexed_chunks: {chunk_count}",
    ]
    if not hits:
        lines.append("")
        lines.append("(no retrieval hits)")
        return "\n".join(lines)

    for i, h in enumerate(hits, 1):
        lines.append("")
        lines.append(
            f"--- {i}. chunk_id={h.chunk_id} "
            f"cosine_sim={h.cosine_similarity:.4f} "
            f"distance={h.distance:.4f} "
            f"norm_score={h.norm_score:.4f} ---"
        )
        lines.append(h.text)
    return "\n".join(lines)


def _run_model(
    *,
    model_label: str,
    encoder_dir: str,
    chunks: list[ChunkRow],
    queries: list[tuple[int, str]],
    top_k: int,
    max_length: int,
) -> dict[int, str]:
    """Return map data_row_index -> report cell text."""
    import chromadb

    use_st = model_label == "Clinical_sBERT"
    if use_st:
        st_valid = Path(encoder_dir).is_dir() and (Path(encoder_dir) / "config.json").is_file()
        if not st_valid:
            raise FileNotFoundError(f"Clinical_sBERT path invalid: {encoder_dir}")
    elif not _encoder_path_looks_valid(encoder_dir):
        raise FileNotFoundError(f"Encoder path invalid: {encoder_dir}")

    tmp_root = Path(tempfile.mkdtemp(prefix=f"emb_cmp_{model_label}_"))
    reports: dict[int, str] = {}
    if use_st:
        backend: EmbeddingBackend | SentenceTransformerBackend = SentenceTransformerBackend(
            encoder_dir
        )
    else:
        backend = EmbeddingBackend(encoder_dir, max_length=max_length)
    try:
        backend.load()
        assert backend.embedding_dim and backend.embedding_dim > 0

        client = chromadb.PersistentClient(
            path=str(tmp_root),
            settings=chromadb.Settings(anonymized_telemetry=False),
        )
        coll = client.get_or_create_collection(
            name="red_flags_emb_benchmark",
            metadata=_COLLECTION_METADATA,
        )

        ids = [c.chunk_id for c in chunks]
        docs = [c.chunk_string for c in chunks]
        embeddings: list[list[float]] = []
        for doc in docs:
            vec = backend.embed(doc)
            if len(vec) != backend.embedding_dim:
                raise RuntimeError(
                    f"Chunk embedding dim {len(vec)} != {backend.embedding_dim}"
                )
            embeddings.append(vec)

        coll.add(ids=ids, documents=docs, embeddings=embeddings)

        for row_idx, query in queries:
            q_emb = backend.embed(query)
            if len(q_emb) != backend.embedding_dim:
                reports[row_idx] = (
                    f"model: {model_label}\n"
                    f"ERROR: query embedding dim {len(q_emb)} "
                    f"!= {backend.embedding_dim}"
                )
                continue
            hits = _query_collection(coll, q_emb, top_k=top_k)
            reports[row_idx] = _format_report(
                model_name=model_label,
                encoder_dir=encoder_dir,
                query=query,
                top_k=top_k,
                chroma_path=str(tmp_root),
                chunk_count=len(chunks),
                embedding_dim=backend.embedding_dim,
                hits=hits,
            )
    finally:
        backend.unload()
        shutil.rmtree(tmp_root, ignore_errors=True)

    return reports


def _settings_rag_top_k() -> int:
    """``settings.rag_top_k`` (``DIGIMSK_RAG_TOP_K`` env / ``app/config.py``)."""
    from app.config import settings

    return settings.rag_top_k


def _configure_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(levelname)s %(message)s",
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
        "tqdm",
    ):
        logging.getLogger(name).setLevel(logging.ERROR if not verbose else logging.WARNING)


def main() -> int:
    _force_hf_offline()
    parser = argparse.ArgumentParser(
        description="Benchmark local embedding models on red-flag RAG retrieval.",
    )
    parser.add_argument("--chunks-csv", type=Path, default=_DEFAULT_CHUNKS)
    parser.add_argument("--results-csv", type=Path, default=_DEFAULT_RESULTS_CSV)
    parser.add_argument("--first-row", type=int, default=2, help="1-based Excel row")
    parser.add_argument("--last-row", type=int, default=11, help="1-based Excel row")
    parser.add_argument(
        "--top-k",
        type=int,
        default=None,
        help="Chroma hits per query (default: app.config settings.rag_top_k)",
    )
    parser.add_argument("--max-length", type=int, default=256)
    parser.add_argument(
        "--models",
        nargs="*",
        default=[],
        help="Subset of model labels (default: all three)",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    top_k = args.top_k if args.top_k is not None else _settings_rag_top_k()
    _configure_logging(args.verbose)
    log = logging.getLogger(__name__)

    chunks = _load_red_flag_chunks(args.chunks_csv)
    log.info("Loaded %d red-flag chunks from %s", len(chunks), args.chunks_csv)

    header, data = _read_results_csv(args.results_csv)
    col_index = {name: i for i, name in enumerate(header)}

    for _label, _path, col_name in _MODELS:
        if col_name not in col_index:
            raise KeyError(
                f"Results CSV missing column {col_name!r}; header={header!r}"
            )

    first_idx = max(0, args.first_row - 2)
    last_idx = min(len(data) - 1, args.last_row - 2)
    if first_idx > last_idx or not data:
        sys.stderr.write("No data rows in the requested row range.\n")
        return 1

    queries: list[tuple[int, str]] = []
    for i in range(first_idx, last_idx + 1):
        row = data[i]
        if len(row) < 2:
            continue
        q = row[1].strip()
        if q:
            queries.append((i, q))

    log.info(
        "Will run %d queries (rows %d-%d) with top_k=%d",
        len(queries),
        args.first_row,
        args.last_row,
        top_k,
    )

    selected = list(_MODELS)
    if args.models:
        allowed = {m.strip() for m in args.models}
        selected = [m for m in _MODELS if m[0] in allowed or m[2] in allowed]
        if not selected:
            sys.stderr.write(f"No models matched --models {args.models!r}\n")
            return 1

    if args.dry_run:
        for label, path, col in selected:
            ok = _encoder_path_looks_valid(path)
            print(f"{label}: {path} valid={ok} -> column {col}")
        return 0

    ncols = len(header)
    for label, encoder_dir, col_name in selected:
        log.info("=== Model %s (%s) ===", label, encoder_dir)
        try:
            reports = _run_model(
                model_label=label,
                encoder_dir=encoder_dir,
                chunks=chunks,
                queries=queries,
                top_k=top_k,
                max_length=args.max_length,
            )
        except Exception as e:
            log.exception("Model %s failed: %s", label, e)
            err_text = f"model: {label}\nERROR: {e}"
            col_i = col_index[col_name]
            for row_idx, _ in queries:
                data[row_idx] = _pad_row(data[row_idx], ncols)
                data[row_idx][col_i] = err_text
            continue

        col_i = col_index[col_name]
        for row_idx, _ in queries:
            data[row_idx] = _pad_row(data[row_idx], ncols)
            data[row_idx][col_i] = reports.get(row_idx, "")

    _write_results_csv(args.results_csv, header, data)
    log.info("Wrote results to %s", args.results_csv)
    return 0


_force_hf_offline()

if __name__ == "__main__":
    raise SystemExit(main())
