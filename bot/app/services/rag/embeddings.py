"""RAG sentence embeddings for Chroma (ingest + query).

Production default: **Clinical_sBERT** via ``sentence_transformers`` (``DIGIMSK_ENCODER_DIR``).
Span NER uses GliNER-BioMed separately (``DIGIMSK_GLINER_MODEL_DIR``).

Optional legacy backend ``hf_mean_pool``: Hugging Face ``AutoModel`` + mean pooling
(GliNER bundle backbone or plain ``config.json``).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Literal

from app.config import settings

_log = logging.getLogger(__name__)

RagEmbeddingBackend = Literal["sentence_transformers", "hf_mean_pool"]

# Cached HF mean-pool encoder
_tok_enc: Any = None
_mdl_enc: Any = None
_device_enc: Any = None

# Cached sentence-transformers model
_st_model: Any = None
_st_dim: int | None = None


def _subdir_with_hf_config(root: Path) -> Path | None:
    for name in ("encoder", "backbone", "baseline", "deberta"):
        p = root / name
        if p.is_dir() and (p / "config.json").is_file():
            return p
    return None


def _sentence_transformer_path_looks_valid(model_dir: str) -> bool:
    root = Path(model_dir)
    return root.is_dir() and (root / "config.json").is_file()


def _hf_mean_pool_path_looks_valid(encoder_dir: str) -> bool:
    root = Path(encoder_dir)
    if not root.is_dir():
        return False
    if (root / "config.json").is_file():
        return True
    if _subdir_with_hf_config(root) is not None:
        return True
    return (root / "gliner_config.json").is_file()


def _resolved_hf_encoder_sources(encoder_dir: str) -> list[tuple[str, bool]]:
    """(HF ``pretrained`` id/path, ``local_files_only``) in try order."""
    root = Path(encoder_dir)
    if not root.is_dir():
        return []
    if (root / "config.json").is_file():
        return [(str(root.resolve()), True)]
    nested = _subdir_with_hf_config(root)
    if nested is not None:
        return [(str(nested.resolve()), True)]
    gl = root / "gliner_config.json"
    if not gl.is_file():
        return []
    try:
        with gl.open(encoding="utf-8") as f:
            gc = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        _log.warning("could not read %s: %s", gl, e)
        return []
    raw = gc.get("model_name") or gc.get("encoder_model_name")
    if not (isinstance(raw, str) and raw.strip()):
        return []
    mid = raw.strip()
    return [(mid, True), (mid, False)]


def rag_embedding_backend() -> RagEmbeddingBackend:
    raw = (settings.rag_embedding_backend or "sentence_transformers").strip().lower()
    if raw in ("hf", "hf_mean_pool", "mean_pool", "deberta", "gliner"):
        return "hf_mean_pool"
    return "sentence_transformers"


def rag_embedding_model_configured() -> bool:
    if rag_embedding_backend() == "sentence_transformers":
        return _sentence_transformer_path_looks_valid(settings.encoder_model_dir)
    return _hf_mean_pool_path_looks_valid(settings.encoder_model_dir)


def embedding_dim_probe() -> int | None:
    """Return configured dim, or probe ST model without retaining cache."""
    if settings.encoder_embedding_dim > 0:
        return settings.encoder_embedding_dim
    if rag_embedding_backend() != "sentence_transformers":
        return None
    path = settings.encoder_model_dir
    if not _sentence_transformer_path_looks_valid(path):
        return None
    try:
        from sentence_transformers import SentenceTransformer

        model = SentenceTransformer(str(Path(path).resolve()), local_files_only=True)
        vec = model.encode("probe", normalize_embeddings=settings.rag_embedding_normalize)
        return int(len(vec))
    except Exception as e:
        _log.debug("embedding dim probe failed: %s", e)
        return None


def unload_embedding_models() -> None:
    """Release cached embedding models (tests / multi-model benchmarks)."""
    global _tok_enc, _mdl_enc, _device_enc, _st_model, _st_dim
    _tok_enc = None
    _mdl_enc = None
    _device_enc = None
    _st_model = None
    _st_dim = None


def _mean_pool(last_hidden: Any, attention_mask: Any) -> Any:
    import torch

    mask = attention_mask.unsqueeze(-1).float()
    summed = (last_hidden * mask).sum(dim=1)
    counts = mask.sum(dim=1).clamp(min=1e-9)
    return summed / counts


def _ensure_hf_mean_pool_encoder(encoder_dir: str) -> bool:
    global _tok_enc, _mdl_enc, _device_enc
    if _mdl_enc is not None and _tok_enc is not None:
        return True
    sources = _resolved_hf_encoder_sources(encoder_dir)
    if not sources:
        return False
    from transformers import AutoModel, AutoTokenizer
    import torch

    last_err: Exception | None = None
    for pretrained, local_only in sources:
        try:
            tok = AutoTokenizer.from_pretrained(pretrained, local_files_only=local_only)
            mdl = AutoModel.from_pretrained(pretrained, local_files_only=local_only)
            mdl.eval()
            _tok_enc = tok
            _mdl_enc = mdl
            _device_enc = torch.device("cuda" if torch.cuda.is_available() else "cpu")
            _mdl_enc.to(_device_enc)
            _log.info(
                "RAG HF mean-pool encoder loaded from %r (local_files_only=%s)",
                pretrained,
                local_only,
            )
            return True
        except Exception as e:
            last_err = e
            _log.debug(
                "HF encoder load failed for %r local_files_only=%s: %s",
                pretrained,
                local_only,
                e,
            )
    if last_err is not None:
        _log.warning("all HF encoder load attempts failed: %s", last_err)
    return False


def _ensure_sentence_transformer(model_dir: str) -> bool:
    global _st_model, _st_dim
    if _st_model is not None:
        return True
    if not _sentence_transformer_path_looks_valid(model_dir):
        return False
    try:
        from sentence_transformers import SentenceTransformer

        path = Path(model_dir).resolve()
        _st_model = SentenceTransformer(str(path), local_files_only=True)
        probe = _st_model.encode(
            "probe",
            normalize_embeddings=settings.rag_embedding_normalize,
        )
        _st_dim = int(len(probe))
        if (
            settings.encoder_embedding_dim > 0
            and _st_dim != settings.encoder_embedding_dim
        ):
            _log.warning(
                "Clinical_sBERT embedding dim %s != DIGIMSK_ENCODER_DIM %s",
                _st_dim,
                settings.encoder_embedding_dim,
            )
        _log.info(
            "RAG sentence-transformers model loaded from %s (dim=%s)",
            path,
            _st_dim,
        )
        return True
    except Exception as e:
        _log.warning("sentence-transformers load failed for %s: %s", model_dir, e)
        return False


def _embed_hf_mean_pool(
    message: str,
    encoder_dir: str,
    max_length: int,
) -> list[float]:
    if not _ensure_hf_mean_pool_encoder(encoder_dir):
        return []
    import torch

    try:
        assert _tok_enc is not None and _mdl_enc is not None and _device_enc is not None
        enc = _tok_enc(
            message,
            return_tensors="pt",
            truncation=True,
            max_length=max_length,
            padding=True,
        )
        enc = {k: v.to(_device_enc) for k, v in enc.items()}
        with torch.no_grad():
            out = _mdl_enc(**enc)
            pooled = _mean_pool(out.last_hidden_state, enc["attention_mask"])
            vec = pooled[0].float().cpu().tolist()
        return list(vec)
    except Exception as e:
        _log.exception("HF mean-pool encode failed: %s", e)
        return []


def _embed_sentence_transformer(message: str, model_dir: str) -> list[float]:
    if not _ensure_sentence_transformer(model_dir):
        return []
    try:
        assert _st_model is not None
        vec = _st_model.encode(
            message,
            normalize_embeddings=settings.rag_embedding_normalize,
        )
        return list(vec.astype(float))
    except Exception as e:
        _log.exception("sentence-transformers encode failed: %s", e)
        return []


def compute_query_embedding(message: str) -> list[float]:
    """Embedding vector for Chroma query/ingest (empty list on failure/skip).

    Uses ``settings.encoder_model_dir``, ``settings.rag_embedding_backend``, and
    ``settings.encoder_max_length`` (HF backend only).
    """
    if not (message and str(message).strip()):
        return []
    model_dir = settings.encoder_model_dir
    if rag_embedding_backend() == "sentence_transformers":
        return _embed_sentence_transformer(message, model_dir)
    return _embed_hf_mean_pool(
        message,
        model_dir,
        max_length=settings.encoder_max_length,
    )
