"""Full-query RAG smoke test on real red-flag chunks with multiple embedding models.

Indexes all ``chunk_string`` rows from the red-flags manual CSV into a **separate**
temporary Chroma collection per model, embeds the full normalized query once, and
compares retrieval across:

- GliNER-BioMed DeBERTa (production RAG encoder)
- Sentence-BERT ``all-MiniLM-L6-v2`` (control)
- Google News Word2Vec 300d via mean word vectors (control)

Default query: ``chunk_string`` from Excel B2 in ``test_chunks.csv`` (same vignette
as the noisy-corpus smoke test).

Writes ``encode_rag_smoke_test_real_results.txt`` and an optional top-k plot PNG.

Run from repo root::

    python "Embeddings test/encode_rag_smoke_test_real.py"
    python "Embeddings test/encode_rag_smoke_test_real.py" --word2vec-path "path/to/GoogleNews-vectors-negative300.bin"
"""

from __future__ import annotations

import argparse
import importlib.util
import logging
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[1]
_EMB_DIR = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_DEFAULT_CORPUS = (
    _ROOT
    / "Knowledge Base"
    / "Red Flags"
    / "chunks"
    / "manual"
    / "red_flags_manual_failsafe - Copy.csv"
)
_DEFAULT_QUERY_CSV = _EMB_DIR / "test_chunks.csv"
_DEFAULT_OUTPUT = _EMB_DIR / "encode_rag_smoke_test_real_results.txt"
_DEFAULT_PLOT = _EMB_DIR / "encode_rag_smoke_test_real_topk.png"

_SMOKE_PATH = _EMB_DIR / "encode_rag_smoke_test.py"
_CMP_PATH = _EMB_DIR / "compare_embedding_models.py"

_DEFAULT_GLINER_DIR = r"E:\DigiMSKbot\GliNER-BioMed"
_DEFAULT_MINILM_DIR = r"E:\DigiMSKbot\all-MiniLM-L6-v2"
_DEFAULT_MINILM_HF = "sentence-transformers/all-MiniLM-L6-v2"
_DEFAULT_WORD2VEC_PATH = r"E:\DigiMSKbot\Google_word2vec\GoogleNews-vectors-negative300.bin"

_QUERY_EXCEL_ROW = 2


def _load_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_smoke = _load_module("encode_rag_smoke_test", _SMOKE_PATH)
_cmp = _load_module("compare_embedding_models", _CMP_PATH)

MethodResult = _smoke.MethodResult
ChunkScore = _smoke.ChunkScore
_configure_logging = _smoke._configure_logging
_build_embedders = _smoke._build_embedders
_ingest_and_retrieve_full_query = _smoke._ingest_and_retrieve_full_query
_settings_rag_top_k = _cmp._settings_rag_top_k
_load_red_flag_chunks = _cmp._load_red_flag_chunks


def _default_query_from_test_chunks_b2(path: Path) -> str:
    import csv

    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    idx = _QUERY_EXCEL_ROW - 2
    if idx < len(rows):
        q = (rows[idx].get("chunk_string") or "").strip()
        if q:
            return q
    return (
        "My back has been hurting for decades, but now I can feel numbness and "
        "tingling around my groin."
    )


def _format_method_section(result: MethodResult, *, plot_label: str) -> list[str]:
    lines: list[str] = [
        "=" * 72,
        f"EMBEDDING MODEL: {plot_label}",
        "=" * 72,
        "",
        result.explanation.strip(),
        "",
        f"top_k (ranked list below): {result.top_k}",
        "",
        "Ranked full-query retrieval:",
    ]
    if not result.ranked_hits:
        lines.append("  (no hits)")
    else:
        for i, h in enumerate(result.ranked_hits, 1):
            lines.append(
                f"  {i}. chunk_id={h.chunk_id} cosine_sim={h.cosine_similarity:.4f} "
                f"distance={h.distance:.4f} norm_score={h.norm_score:.4f}"
            )
            preview = (h.text[:200] + "...") if len(h.text) > 200 else h.text
            lines.append(f"     {preview}")

    lines.extend(
        [
            "",
            "Cosine similarity vs corpus index (all indexed chunks, CSV order):",
            "  corpus_idx | chunk_id | cosine_sim",
        ]
    )
    for s in sorted(result.all_scores, key=lambda x: x.noise_step):
        lines.append(
            f"  {s.noise_step:10d} | {s.chunk_id:<8s} | {s.cosine_sim:.4f}"
        )
    lines.append("")
    return lines


def _write_topk_plot(
    results: list[tuple[str, MethodResult]],
    plot_path: Path,
    *,
    top_n: int,
) -> bool:
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        logging.getLogger(__name__).warning("matplotlib not installed; skipping plot")
        return False

    markers = ["o-", "s--", "^-", "D-.", "v:"]
    fig, ax = plt.subplots(figsize=(10, 5.5))
    for i, (label, result) in enumerate(results):
        hits = result.ranked_hits[:top_n]
        if not hits:
            continue
        xs = list(range(1, len(hits) + 1))
        ys = [h.cosine_similarity for h in hits]
        style = markers[i % len(markers)]
        ax.plot(xs, ys, style, label=label, linewidth=1.5, markersize=5)

    ax.set_xlabel(f"Retrieval rank (1 = best, top {top_n})")
    ax.set_ylabel("Cosine similarity (full-query vs chunk)")
    ax.set_title(
        "Full-query retrieval on red-flag corpus "
        "(one temp Chroma per model; query = test_chunks.csv B2)"
    )
    ax.legend(loc="best", fontsize=7)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    plot_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(plot_path, dpi=150)
    plt.close(fig)
    return True


def run_smoke_test_real(
    *,
    corpus_csv: Path,
    query_csv: Path,
    output_path: Path,
    plot_path: Path | None,
    user_query: str,
    embedders: list[Any],
    top_k: int,
    plot_top_n: int,
) -> tuple[str, bool]:
    from app.services.preprocess import normalize_user_text

    chunks = _load_red_flag_chunks(corpus_csv)
    ordered_ids = [c.chunk_id for c in chunks]
    normalized = normalize_user_text(user_query)

    tmp_root = Path(tempfile.mkdtemp(prefix="emb_rag_smoke_real_"))
    results: list[tuple[str, MethodResult]] = []
    errors: list[str] = []

    try:
        for embedder in embedders:
            log = logging.getLogger(__name__)
            log.info("=== %s ===", embedder.label)
            try:
                embedder.load()
                result = _ingest_and_retrieve_full_query(
                    embedder,
                    chunks,
                    normalized,
                    top_k=top_k,
                    ordered_ids=ordered_ids,
                    tmp_parent=tmp_root,
                )
                results.append((embedder.label, result))
            except Exception as e:
                errors.append(f"{embedder.label}: {e}")
                log.exception("Model %s failed: %s", embedder.label, e)
            finally:
                embedder.unload()

        plot_written = False
        if plot_path is not None and results:
            plot_written = _write_topk_plot(
                results,
                plot_path,
                top_n=min(plot_top_n, top_k),
            )

        header = [
            "encode_rag_smoke_test_real",
            "retrieval: full-query only (entire normalized message embedded once)",
            f"corpus: {corpus_csv.name} ({len(chunks)} chunks)",
            f"query_source: test_chunks.csv Excel B{_QUERY_EXCEL_ROW}",
            f"user_query: {user_query!r}",
            f"normalized: {normalized!r}",
            f"models_run: {len(results)}",
            "",
        ]
        if errors:
            header.extend(["Models skipped (errors):", *[f"  - {e}" for e in errors], ""])

        body: list[str] = list(header)
        for label, result in results:
            body.extend(_format_method_section(result, plot_label=label))

        if plot_path is not None:
            if plot_written:
                body.append(f"Top-k plot: {plot_path}")
            else:
                body.append(f"Plot not written (install matplotlib). Path: {plot_path}")

        report = "\n".join(body)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(report + "\n", encoding="utf-8")
        has_hits = any(r.ranked_hits for _, r in results)
        return report, has_hits
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Full-query red-flag corpus test with DeBERTa, MiniLM, and Word2Vec."
        ),
    )
    parser.add_argument("--corpus-csv", type=Path, default=_DEFAULT_CORPUS)
    parser.add_argument(
        "--query-csv",
        type=Path,
        default=_DEFAULT_QUERY_CSV,
        help="CSV used for default query (Excel B2 chunk_string)",
    )
    parser.add_argument("--output", type=Path, default=_DEFAULT_OUTPUT)
    parser.add_argument("--plot", type=Path, default=_DEFAULT_PLOT)
    parser.add_argument("--no-plot", action="store_true")
    parser.add_argument(
        "--query",
        nargs="?",
        const="",
        default=None,
        metavar="TEXT",
        help=(
            "User message. Omit --query, use ``--query`` alone, or pass an empty "
            "value to use chunk_string from Excel B2 in --query-csv"
        ),
    )
    parser.add_argument("--top-k", type=int, default=None)
    parser.add_argument(
        "--plot-top-n",
        type=int,
        default=20,
        help="Number of top ranks to show in the PNG (default: 20)",
    )
    parser.add_argument("--max-length", type=int, default=256)
    parser.add_argument(
        "--gliner-dir",
        default=None,
        help=f"GliNER-BioMed / DeBERTa path (default: DIGIMSK_ENCODER_DIR or {_DEFAULT_GLINER_DIR})",
    )
    parser.add_argument(
        "--minilm-dir",
        default=None,
        help=f"Local all-MiniLM-L6-v2 folder or HF id (default: {_DEFAULT_MINILM_DIR} or HF)",
    )
    parser.add_argument(
        "--word2vec-path",
        default=None,
        help=f"GoogleNews .bin path (default: {_DEFAULT_WORD2VEC_PATH} if exists)",
    )
    parser.add_argument(
        "--models",
        nargs="*",
        default=[],
        help="Subset: gliner deberta minilm sbert word2vec (default: all available)",
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    _configure_logging(verbose=args.verbose)
    log = logging.getLogger(__name__)

    from app.config import settings

    corpus_csv = args.corpus_csv.resolve()
    if not corpus_csv.is_file():
        log.error("Corpus CSV not found: %s", corpus_csv)
        return 1

    query_csv = args.query_csv.resolve()
    if not query_csv.is_file():
        log.error("Query CSV not found: %s", query_csv)
        return 1

    gliner_dir = args.gliner_dir or settings.encoder_model_dir
    minilm_path = args.minilm_dir or _DEFAULT_MINILM_DIR
    if not Path(minilm_path).is_dir():
        minilm_path = _DEFAULT_MINILM_HF

    w2v_path = args.word2vec_path
    if w2v_path is None and Path(_DEFAULT_WORD2VEC_PATH).is_file():
        w2v_path = _DEFAULT_WORD2VEC_PATH

    top_k = args.top_k if args.top_k is not None else _settings_rag_top_k()
    if args.query is None or not str(args.query).strip():
        user_query = _default_query_from_test_chunks_b2(query_csv).strip()
        log.info("Using default query from %s B%d", query_csv.name, _QUERY_EXCEL_ROW)
    else:
        user_query = str(args.query).strip()
    if not user_query:
        sys.stderr.write(
            f"Query is empty and B{_QUERY_EXCEL_ROW} chunk_string in "
            f"{query_csv.name} is empty.\n"
        )
        return 1

    try:
        embedders = _build_embedders(
            gliner_dir=gliner_dir,
            minilm_path=minilm_path,
            word2vec_path=w2v_path,
            max_length=args.max_length,
            models=args.models,
        )
    except ValueError as e:
        sys.stderr.write(f"{e}\n")
        return 1

    output_path = args.output.resolve()
    plot_path = None if args.no_plot else args.plot.resolve()

    log.info("Full-query real-corpus smoke test: %s", ", ".join(e.label for e in embedders))

    try:
        report, has_hits = run_smoke_test_real(
            corpus_csv=corpus_csv,
            query_csv=query_csv,
            output_path=output_path,
            plot_path=plot_path,
            user_query=user_query,
            embedders=embedders,
            top_k=top_k,
            plot_top_n=args.plot_top_n,
        )
    except Exception as e:
        log.exception("Smoke test failed: %s", e)
        sys.stderr.write(f"ERROR: {e}\n")
        return 1

    try:
        sys.stdout.write(report + "\n")
    except UnicodeEncodeError:
        sys.stdout.buffer.write((report + "\n").encode("utf-8", errors="replace"))
    log.info("Wrote %s", output_path)
    if not embedders:
        return 1
    return 0 if has_hits else 2


if __name__ == "__main__":
    raise SystemExit(main())
