"""Pooled query embeddings for Chroma (same HF encoder/dimension as ingested chunks)."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from app.config import settings

_log = logging.getLogger(__name__)

# cached model instances to avoid reloading
_tok_enc: Any = None
_mdl_enc: Any = None
_device_enc: Any = None


def _subdir_with_hf_config(root: Path) -> Path | None:
    for name in ("encoder", "backbone", "baseline", "deberta"):
        p = root / name
        if p.is_dir() and (p / "config.json").is_file():
            return p
    return None


def _encoder_path_looks_valid(encoder_dir: str) -> bool:
    root = Path(encoder_dir)
    if not root.is_dir():
        return False
    if (root / "config.json").is_file():
        return True
    if _subdir_with_hf_config(root) is not None:
        return True
    return (root / "gliner_config.json").is_file()


def _resolved_encoder_sources(encoder_dir: str) -> list[tuple[str, bool]]:
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


def rag_embedding_model_configured() -> bool:
    return _encoder_path_looks_valid(settings.encoder_model_dir)


# mean pooling operation to convert sequence of token embeddings into a single vector
def _mean_pool(last_hidden: Any, attention_mask: Any) -> Any:
    import torch

    mask = attention_mask.unsqueeze(-1).float()
    summed = (last_hidden * mask).sum(dim=1)
    counts = mask.sum(dim=1).clamp(min=1e-9)
    return summed / counts


# ensure encoder is properly configured
def _ensure_encoder(encoder_dir: str) -> bool:
    global _tok_enc, _mdl_enc, _device_enc
    # if encoder is already loaded, return True
    if _mdl_enc is not None and _tok_enc is not None:
        return True
    sources = _resolved_encoder_sources(encoder_dir)
    if not sources:
        return False
    # lazy imports for heavy dependencies
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
                "RAG encoder backbone loaded from %r (local_files_only=%s)",
                pretrained,
                local_only,
            )
            return True
        except Exception as e:
            last_err = e
            _log.debug(
                "encoder load failed for %r local_files_only=%s: %s",
                pretrained,
                local_only,
                e,
            )
    if last_err is not None:
        _log.warning("all encoder load attempts failed: %s", last_err)
    return False


# runs sentence encoder (tokenizer + AutoModel), mean-pools token hidden states (respecting the attention mask),
# and returns that vector as a Python list of floats for RAG indexing
def _embed_query_to_list(
    message: str,
    encoder_dir: str,
    max_length: int = 256,
) -> list[float]:
    if not (message and str(message).strip()):  # if message is empty, return empty embedding
        return []
    if not _ensure_encoder(encoder_dir):  # if encoder not properly configured, return empty embedding
        return []
    import torch

    try:
        assert _tok_enc is not None and _mdl_enc is not None and _device_enc is not None
        enc = _tok_enc(
            message,
            return_tensors="pt",  # return PyTorch tensors- expected by _mdl_enc
            truncation=True,  # cut off if > max_length tokens
            max_length=max_length,
            padding=True,  # pad input to max length
        )
        enc = {k: v.to(_device_enc) for k, v in enc.items()}  # move tensors to appropriate device
        with torch.no_grad():  # disable gradient tracking for inference
            out = _mdl_enc(**enc)  # forward pass through encoder
            pooled = _mean_pool(out.last_hidden_state, enc["attention_mask"])  # pools real per-token vectors into query embedding
            vec = pooled[0].float().cpu().tolist()  # take off GPU and convert to list of floats for RAG indexing
        return list(vec)
    except Exception as e:
        _log.exception("local encode failed: %s", e)
        return []


# thin wrapper around _embed_query_to_list
def compute_query_embedding(message: str) -> list[float]:
    """Mean-pooled query vector for Chroma (empty list on failure/skip).

    Uses ``settings.encoder_model_dir`` and ``settings.encoder_max_length``.
    """
    return _embed_query_to_list(
        message,
        settings.encoder_model_dir,
        max_length=settings.encoder_max_length,
    )
