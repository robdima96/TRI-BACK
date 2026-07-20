"""Full-query RAG smoke test on ``test_chunks.csv`` with multiple embedding models.

Indexes Excel B2–B21 into a **separate** temporary Chroma collection per model, embeds
the full normalized query once, and compares retrieval across:

- **Clinical_sBERT** (production RAG via ``app.services.rag.embeddings`` / ``DIGIMSK_ENCODER_DIR``)
- GliNER-BioMed DeBERTa mean-pool (legacy RAG baseline; optional)
- Sentence-BERT ``all-MiniLM-L6-v2`` (control)
- Google News Word2Vec 300d (control, optional)

Production chatbot flow: GliNER spans for NER (**``DIGIMSK_GLINER_MODEL_DIR``**), Clinical_sBERT
for Chroma vectors (**``DIGIMSK_ENCODER_DIR``**). This script uses **full-query** embedding only
(not per-entity phrases); see ``compare_embedding_models_entities.py`` for entity-level retrieval.

Writes ``encode_rag_smoke_test_results.txt`` and a cosine-vs-noise-step PNG.

Run from repo root::

    python "Embeddings test/encode_rag_smoke_test.py"
    python "Embeddings test/encode_rag_smoke_test.py" --models production minilm
"""

from __future__ import annotations

import argparse
import importlib.util
import logging
import os
import re
import shutil
import sys
import tempfile
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

_ROOT = Path(__file__).resolve().parents[1]
_EMB_DIR = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_DEFAULT_CSV = _EMB_DIR / "test_chunks.csv"
_DEFAULT_OUTPUT = _EMB_DIR / "encode_rag_smoke_test_results.txt"
_DEFAULT_PLOT = _EMB_DIR / "encode_rag_smoke_test_monotonicity.png"
_CMP_PATH = _EMB_DIR / "compare_embedding_models.py"

_DEFAULT_CLINICAL_SBERT_DIR = r"E:\DigiMSKbot\Clinical_sBERT"
_DEFAULT_GLINER_DIR = r"E:\DigiMSKbot\GliNER-BioMed"
_DEFAULT_MINILM_DIR = r"E:\DigiMSKbot\all-MiniLM-L6-v2"
_DEFAULT_MINILM_HF = "sentence-transformers/all-MiniLM-L6-v2"
_DEFAULT_WORD2VEC_PATH = r"E:\DigiMSKbot\Google_word2vec\GoogleNews-vectors-negative300.bin"

_FIRST_EXCEL_ROW = 2
_LAST_EXCEL_ROW = 21

_COLLECTION_METADATA = {"hnsw:space": "cosine"}

FULL_QUERY_EXPLANATION_TEMPLATE = """\
FULL-QUERY RETRIEVAL — {label}
--------------------------------
Model source: {source}
Mechanism: {mechanism}
Embedding dimension: {dim}

1. The user message is normalized (lowercase, whitespace cleanup).
2. The **entire** normalized string is embedded **once** with this model.
3. That vector is compared to every indexed chunk in a dedicated Chroma collection
   (cosine space; one temp DB per model because dimensions differ).
4. Chroma returns closest chunks; cosine_sim = 1 - distance.

For the noise corpus (r_1 clean -> r_20 noisiest), a fair monotonicity check plots
cosine_sim vs noise step n. Expect scores to fall as noise increases if extra text
dilutes similarity to the clean query — especially for semantic encoders."""


class TextEmbedder(ABC):
    label: str
    source: str
    mechanism: str

    @property
    @abstractmethod
    def embedding_dim(self) -> int:
        ...

    @abstractmethod
    def load(self) -> None:
        ...

    @abstractmethod
    def unload(self) -> None:
        ...

    @abstractmethod
    def embed(self, text: str) -> list[float]:
        ...

    def explanation(self) -> str:
        return FULL_QUERY_EXPLANATION_TEMPLATE.format(
            label=self.label,
            source=self.source,
            mechanism=self.mechanism,
            dim=self.embedding_dim,
        )


class ProductionClinicalSbertEmbedder(TextEmbedder):
    """Production RAG path: ``compute_query_embedding`` (Clinical_sBERT + settings)."""

    def __init__(self) -> None:
        from app.config import settings

        self.label = "Clinical_sBERT (production RAG)"
        self.source = settings.encoder_model_dir
        self.mechanism = (
            "``app.services.rag.embeddings.compute_query_embedding`` — "
            f"backend={settings.rag_embedding_backend!r}, "
            f"normalize={settings.rag_embedding_normalize}."
        )
        self._dim = settings.encoder_embedding_dim

    @property
    def embedding_dim(self) -> int:
        return self._dim

    def load(self) -> None:
        from app.services.rag.embeddings import (
            embedding_dim_probe,
            rag_embedding_model_configured,
            unload_embedding_models,
        )

        unload_embedding_models()
        if not rag_embedding_model_configured():
            raise FileNotFoundError(
                f"Production RAG encoder not configured: {self.source}"
            )
        probed = embedding_dim_probe()
        if probed is not None:
            self._dim = probed

    def unload(self) -> None:
        from app.services.rag.embeddings import unload_embedding_models

        unload_embedding_models()

    def embed(self, text: str) -> list[float]:
        from app.services.rag.embeddings import compute_query_embedding

        return compute_query_embedding(text)


class DebertaGlinerEmbedder(TextEmbedder):
    def __init__(self, encoder_dir: str, *, max_length: int = 256) -> None:
        self.label = "GliNER-BioMed DeBERTa (legacy RAG)"
        self.source = encoder_dir
        self.mechanism = (
            "Mean-pooled Hugging Face DeBERTa backbone from the GliNER-BioMed bundle "
            "(legacy ``hf_mean_pool`` RAG; not production since Clinical_sBERT)."
        )
        self._encoder_dir = encoder_dir
        self._max_length = max_length
        self._backend: Any = None

    @property
    def embedding_dim(self) -> int:
        if self._backend is None or self._backend.embedding_dim is None:
            return 768
        return int(self._backend.embedding_dim)

    def load(self) -> None:
        _force_hf_offline()
        if not _encoder_path_looks_valid(self._encoder_dir):
            raise FileNotFoundError(f"Encoder path invalid: {self._encoder_dir}")
        self._backend = EmbeddingBackend(self._encoder_dir, max_length=self._max_length)
        self._backend.load()

    def unload(self) -> None:
        if self._backend is not None:
            self._backend.unload()
            self._backend = None

    def embed(self, text: str) -> list[float]:
        assert self._backend is not None
        return self._backend.embed(text)


class SentenceTransformerEmbedder(TextEmbedder):
    def __init__(self, model_path: str) -> None:
        self.label = "Sentence-BERT all-MiniLM-L6-v2"
        self.source = model_path
        self.mechanism = (
            "``sentence_transformers`` encode() on the full sentence; "
            "384-d embedding (see "
            "https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2)."
        )
        self._model_path = model_path
        self._model: Any = None
        self._dim = 384

    @property
    def embedding_dim(self) -> int:
        return self._dim

    def load(self) -> None:
        _force_hf_offline()
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        from sentence_transformers import SentenceTransformer

        path = Path(self._model_path)
        if path.is_dir() and (path / "config.json").is_file():
            self._model = SentenceTransformer(str(path.resolve()), local_files_only=True)
        else:
            self._model = SentenceTransformer(
                self._model_path,
                local_files_only=True,
            )
        probe = self._model.encode("probe", normalize_embeddings=True)
        self._dim = int(len(probe))

    def unload(self) -> None:
        self._model = None

    def embed(self, text: str) -> list[float]:
        if not (text and str(text).strip()):
            return []
        assert self._model is not None
        vec = self._model.encode(text, normalize_embeddings=True)
        return list(vec.astype(float))


class Word2VecEmbedder(TextEmbedder):
    """Mean of Google News Word2Vec vectors for in-vocabulary tokens (control)."""

    def __init__(self, vectors_path: str) -> None:
        self.label = "Word2Vec Google News 300d (control)"
        self.source = vectors_path
        self.mechanism = (
            "Tokenize on word regex, average pretrained Word2Vec vectors for known "
            "tokens (gensim KeyedVectors). OOV tokens skipped. Control baseline "
            "per Kaggle Word2Vec tutorials (e.g. bavalpreet26/word2vec-pretrained); "
            "not semantic sentence encoders."
        )
        self._vectors_path = vectors_path
        self._kv: Any = None
        self._dim = 300

    @property
    def embedding_dim(self) -> int:
        return self._dim

    def load(self) -> None:
        from gensim.models import KeyedVectors

        path = Path(self._vectors_path)
        if not path.is_file():
            raise FileNotFoundError(
                f"Word2Vec vectors not found: {path}. "
                "Download GoogleNews-vectors-negative300.bin or pass --word2vec-path."
            )
        self._kv = KeyedVectors.load_word2vec_format(str(path), binary=True)
        self._dim = int(self._kv.vector_size)

    def unload(self) -> None:
        self._kv = None

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        return re.findall(r"[a-zA-Z0-9']+", text.lower())

    def embed(self, text: str) -> list[float]:
        if not (text and str(text).strip()) or self._kv is None:
            return []
        vectors = [
            self._kv[word]
            for word in self._tokenize(text)
            if word in self._kv
        ]
        if not vectors:
            return [0.0] * self._dim
        mean = np.mean(vectors, axis=0)
        return list(mean.astype(float))


@dataclass(frozen=True)
class ChunkScore:
    noise_step: int
    chunk_id: str
    cosine_sim: float
    excel_row: int


@dataclass
class MethodResult:
    name: str
    explanation: str
    top_k: int
    ranked_hits: list[Any]
    all_scores: list[ChunkScore] = field(default_factory=list)
    spearman_noise_vs_cosine: float | None = None
    monotonic_decreasing: bool = False


def _load_compare_module() -> Any:
    spec = importlib.util.spec_from_file_location("compare_embedding_models", _CMP_PATH)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {_CMP_PATH}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["compare_embedding_models"] = mod
    spec.loader.exec_module(mod)
    return mod


_cmp = _load_compare_module()
ChunkRow = _cmp.ChunkRow
EmbeddingBackend = _cmp.EmbeddingBackend
RetrievalHit = _cmp.RetrievalHit
_query_collection = _cmp._query_collection
_force_hf_offline = _cmp._force_hf_offline
_settings_rag_top_k = _cmp._settings_rag_top_k
_encoder_path_looks_valid = _cmp._encoder_path_looks_valid


def _configure_logging(*, verbose: bool) -> None:
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
        "sentence_transformers",
        "gensim",
        "filelock",
        "gliner",
        "tqdm",
        "matplotlib",
    ):
        logging.getLogger(name).setLevel(
            logging.ERROR if not verbose else logging.WARNING
        )


def _load_test_chunks_b2_b21(path: Path) -> list[ChunkRow]:
    import csv

    rows: list[ChunkRow] = []
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        all_rows = list(reader)
    for excel_row in range(_FIRST_EXCEL_ROW, _LAST_EXCEL_ROW + 1):
        idx = excel_row - 2
        if idx < 0 or idx >= len(all_rows):
            continue
        raw = all_rows[idx]
        cid = (raw.get("chunk_id") or f"row_{excel_row}").strip()
        text = (raw.get("chunk_string") or "").strip()
        if cid and text:
            rows.append(ChunkRow(chunk_id=cid, chunk_string=text))
    if not rows:
        raise ValueError(
            f"No non-empty chunk_string rows for Excel B{_FIRST_EXCEL_ROW}–"
            f"B{_LAST_EXCEL_ROW} in {path}"
        )
    return rows


def _default_query_from_csv(path: Path) -> str:
    import csv

    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    idx = _FIRST_EXCEL_ROW - 2
    if idx < len(rows):
        q = (rows[idx].get("chunk_string") or "").strip()
        if q:
            return q
    return (
        "My back has been hurting for decades, but now I can feel numbess and "
        "tingling around my groin."
    )


def _rank_correlation(x: list[float], y: list[float]) -> float | None:
    if len(x) < 3 or len(x) != len(y):
        return None
    rx = np.argsort(np.argsort(x)).astype(float)
    ry = np.argsort(np.argsort(y)).astype(float)
    if np.std(rx) < 1e-9 or np.std(ry) < 1e-9:
        return None
    return float(np.corrcoef(rx, ry)[0, 1])


def _build_chunk_scores(
    hits: list[RetrievalHit],
    ordered_ids: list[str],
) -> list[ChunkScore]:
    by_id = {h.chunk_id: h.cosine_similarity for h in hits}
    out: list[ChunkScore] = []
    for step, cid in enumerate(ordered_ids):
        if cid not in by_id:
            continue
        out.append(
            ChunkScore(
                noise_step=step,
                chunk_id=cid,
                cosine_sim=by_id[cid],
                excel_row=_FIRST_EXCEL_ROW + step,
            )
        )
    return out


def _analyze_monotonicity(scores: list[ChunkScore]) -> tuple[float | None, bool]:
    if len(scores) < 2:
        return None, False
    steps = [s.noise_step for s in scores]
    cosines = [s.cosine_sim for s in scores]
    rho = _rank_correlation(steps, cosines)
    ordered = sorted(scores, key=lambda s: s.noise_step)
    monotonic = all(
        ordered[i].cosine_sim >= ordered[i + 1].cosine_sim
        for i in range(len(ordered) - 1)
    )
    return rho, monotonic


def _ingest_and_retrieve_full_query(
    embedder: TextEmbedder,
    chunks: list[ChunkRow],
    query_text: str,
    *,
    top_k: int,
    ordered_ids: list[str],
    tmp_parent: Path,
) -> MethodResult:
    import chromadb

    coll_name = f"test_chunks_{re.sub(r'[^a-z0-9]+', '_', embedder.label.lower())[:40]}"
    chroma_dir = tmp_parent / coll_name
    client = chromadb.PersistentClient(
        path=str(chroma_dir),
        settings=chromadb.Settings(anonymized_telemetry=False),
    )
    coll = client.get_or_create_collection(
        name="chunks",
        metadata=_COLLECTION_METADATA,
    )

    ids = [c.chunk_id for c in chunks]
    docs = [c.chunk_string for c in chunks]
    embeddings = [embedder.embed(doc) for doc in docs]
    dim = embedder.embedding_dim
    for i, vec in enumerate(embeddings):
        if len(vec) != dim:
            raise RuntimeError(
                f"{embedder.label}: chunk {ids[i]} dim {len(vec)} != {dim}"
            )
    coll.add(ids=ids, documents=docs, embeddings=embeddings)

    n_all = coll.count()
    q_emb = embedder.embed(query_text)
    if len(q_emb) != dim:
        raise RuntimeError(f"{embedder.label}: query embedding dim {len(q_emb)} != {dim}")

    hits_ranked = _query_collection(coll, q_emb, top_k=top_k)
    hits_all = _query_collection(coll, q_emb, top_k=n_all)
    all_scores = _build_chunk_scores(hits_all, ordered_ids)
    rho, mono = _analyze_monotonicity(all_scores)

    slug = re.sub(r"[^a-z0-9]+", "_", embedder.label.lower()).strip("_")[:32]
    return MethodResult(
        name=slug,
        explanation=embedder.explanation(),
        top_k=top_k,
        ranked_hits=hits_ranked,
        all_scores=all_scores,
        spearman_noise_vs_cosine=rho,
        monotonic_decreasing=mono,
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
            step = next(
                (s.noise_step for s in result.all_scores if s.chunk_id == h.chunk_id),
                -1,
            )
            lines.append(
                f"  {i}. chunk_id={h.chunk_id} noise_step={step} "
                f"cosine_sim={h.cosine_similarity:.4f} distance={h.distance:.4f} "
                f"norm_score={h.norm_score:.4f}"
            )
            preview = (h.text[:200] + "...") if len(h.text) > 200 else h.text
            lines.append(f"     {preview}")

    lines.extend(
        [
            "",
            "Cosine similarity vs noise step (all indexed chunks):",
            "  noise_step | excel_row | chunk_id | cosine_sim",
            "  (step 0 = clean r_1 / B2; higher step = more noise)",
        ]
    )
    for s in sorted(result.all_scores, key=lambda x: x.noise_step):
        lines.append(
            f"  {s.noise_step:10d} | B{s.excel_row:<8d} | {s.chunk_id:<6s} | {s.cosine_sim:.4f}"
        )

    if result.spearman_noise_vs_cosine is not None:
        lines.append("")
        lines.append(
            f"Spearman rank correlation (noise_step vs cosine_sim): "
            f"{result.spearman_noise_vs_cosine:.4f}"
        )
        lines.append(
            "  -1 = cosine tends to fall as noise increases; +1 = rises with noise."
        )
    lines.append(
        f"Strictly decreasing cosine step 0 -> max: "
        f"{'YES' if result.monotonic_decreasing else 'NO'}"
    )
    lines.append("")
    return lines


def _write_monotonicity_plot(
    results: list[tuple[str, MethodResult]],
    plot_path: Path,
) -> bool:
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        logging.getLogger(__name__).warning("matplotlib not installed; skipping plot")
        return False

    markers = ["o-", "s--", "^-", "D-.", "v:"]
    fig, ax = plt.subplots(figsize=(10, 5.5))
    for i, (label, result) in enumerate(results):
        if not result.all_scores:
            continue
        xs = [s.noise_step for s in sorted(result.all_scores, key=lambda x: x.noise_step)]
        ys = [s.cosine_sim for s in sorted(result.all_scores, key=lambda x: x.noise_step)]
        style = markers[i % len(markers)]
        ax.plot(xs, ys, style, label=label, linewidth=1.5, markersize=5)

    ax.set_xlabel("Noise step n (0 = clean r_1 / B2; 19 = noisiest r_20 / B21)")
    ax.set_ylabel("Cosine similarity (full-query vs each chunk)")
    ax.set_title(
        "Full-query retrieval: cosine vs noise (test_chunks.csv, one Chroma per model)"
    )
    ax.legend(loc="best", fontsize=7)
    ax.grid(True, alpha=0.3)
    ax.set_xticks(range(0, 20, 2))
    fig.tight_layout()
    plot_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(plot_path, dpi=150)
    plt.close(fig)
    return True


def _build_embedders(
    *,
    gliner_dir: str,
    minilm_path: str,
    word2vec_path: str | None,
    max_length: int,
    models: list[str],
) -> list[TextEmbedder]:
    catalog: dict[str, TextEmbedder] = {
        "production": ProductionClinicalSbertEmbedder(),
        "clinical_sbert": ProductionClinicalSbertEmbedder(),
        "clinical-sbert": ProductionClinicalSbertEmbedder(),
        "gliner": DebertaGlinerEmbedder(gliner_dir, max_length=max_length),
        "deberta": DebertaGlinerEmbedder(gliner_dir, max_length=max_length),
        "legacy-deberta": DebertaGlinerEmbedder(gliner_dir, max_length=max_length),
        "minilm": SentenceTransformerEmbedder(minilm_path),
        "sbert": SentenceTransformerEmbedder(minilm_path),
        "sentence-transformers": SentenceTransformerEmbedder(minilm_path),
    }
    if word2vec_path:
        catalog["word2vec"] = Word2VecEmbedder(word2vec_path)
        catalog["w2v"] = Word2VecEmbedder(word2vec_path)

    if not models:
        keys = ["production", "minilm"]
        if word2vec_path:
            keys.append("word2vec")
        models = keys

    out: list[TextEmbedder] = []
    seen: set[str] = set()
    for key in models:
        k = key.strip().lower()
        if k in seen:
            continue
        if k not in catalog:
            raise ValueError(
                f"Unknown model {key!r}; choose from {sorted(catalog)}"
            )
        seen.add(k)
        out.append(catalog[k])
    return out


def run_smoke_test(
    *,
    chunks_csv: Path,
    output_path: Path,
    plot_path: Path | None,
    user_query: str,
    embedders: list[TextEmbedder],
    top_k: int,
) -> tuple[str, bool]:
    from app.services.preprocess import normalize_user_text

    chunks = _load_test_chunks_b2_b21(chunks_csv)
    ordered_ids = [c.chunk_id for c in chunks]
    normalized = normalize_user_text(user_query)

    tmp_root = Path(tempfile.mkdtemp(prefix="emb_rag_smoke_multi_"))
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
            plot_written = _write_monotonicity_plot(results, plot_path)

        header = [
            "encode_rag_smoke_test",
            "retrieval: full-query only (entire normalized message embedded once)",
            f"corpus: test_chunks.csv (Excel B{_FIRST_EXCEL_ROW}–B{_LAST_EXCEL_ROW})",
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
                body.append(f"Monotonicity plot: {plot_path}")
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
            "Full-query noisy-chunk test: production Clinical_sBERT, optional "
            "legacy GliNER DeBERTa, MiniLM, Word2Vec."
        ),
    )
    parser.add_argument("--chunks-csv", type=Path, default=_DEFAULT_CSV)
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
            "value to use chunk_string from Excel B2 in test_chunks.csv"
        ),
    )
    parser.add_argument("--top-k", type=int, default=None)
    parser.add_argument("--max-length", type=int, default=256)
    parser.add_argument(
        "--gliner-dir",
        default=None,
        help=f"Legacy GliNER-BioMed mean-pool path (default: {_DEFAULT_GLINER_DIR})",
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
        help=(
            "Subset: production clinical_sbert gliner deberta minilm sbert word2vec "
            "(default: production + minilm [+ word2vec if path exists])"
        ),
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    _configure_logging(verbose=args.verbose)
    log = logging.getLogger(__name__)

    from app.config import settings

    chunks_csv = args.chunks_csv.resolve()
    if not chunks_csv.is_file():
        log.error("CSV not found: %s", chunks_csv)
        return 1

    gliner_dir = args.gliner_dir or _DEFAULT_GLINER_DIR
    minilm_path = args.minilm_dir or _DEFAULT_MINILM_DIR
    if not Path(minilm_path).is_dir():
        minilm_path = _DEFAULT_MINILM_HF

    w2v_path = args.word2vec_path
    if w2v_path is None and Path(_DEFAULT_WORD2VEC_PATH).is_file():
        w2v_path = _DEFAULT_WORD2VEC_PATH

    top_k = args.top_k if args.top_k is not None else _settings_rag_top_k()
    if args.query is None or not str(args.query).strip():
        user_query = _default_query_from_csv(chunks_csv).strip()
        log.info("Using default query from test_chunks.csv B2")
    else:
        user_query = str(args.query).strip()
    if not user_query:
        sys.stderr.write(
            "Query is empty and B2 chunk_string in test_chunks.csv is empty.\n"
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

    log.info("Full-query smoke test: %s", ", ".join(e.label for e in embedders))

    try:
        report, has_hits = run_smoke_test(
            chunks_csv=chunks_csv,
            output_path=output_path,
            plot_path=plot_path,
            user_query=user_query,
            embedders=embedders,
            top_k=top_k,
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
