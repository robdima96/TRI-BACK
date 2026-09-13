"""Load and run the local Mistral instruct model."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

_log = logging.getLogger(__name__)

_tokenizer: Any = None
_model: Any = None
_model_dir: str | None = None


def model_path_valid(model_dir: str | Path) -> bool:
    root = Path(model_dir)
    if not root.is_dir():
        return False
    return any(root.glob("*.safetensors")) or (root / "model.safetensors").is_file()


def load_model(model_dir: str | Path) -> None:
    """Load tokenizer and causal LM once (cached until model_dir changes)."""
    global _tokenizer, _model, _model_dir
    path = str(Path(model_dir).resolve())
    if _model is not None and _tokenizer is not None and _model_dir == path:
        return
    if not model_path_valid(path):
        raise FileNotFoundError(
            f"Local model not found or missing weights: {path}\n"
            "Expected *.safetensors in the model directory."
        )

    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    _log.info("Loading model from %s (this may take a minute)...", path)
    _tokenizer = AutoTokenizer.from_pretrained(path, local_files_only=True)
    _model = AutoModelForCausalLM.from_pretrained(
        path,
        torch_dtype=torch.float16,
        device_map="auto",
        local_files_only=True,
    )
    _model_dir = path
    _log.info("Model loaded.")


def generate_reply(
    messages: list[dict[str, str]],
    *,
    model_dir: str | Path,
    max_new_tokens: int = 500,
    temperature: float = 0.2,
    top_p: float = 0.9,
) -> str:
    """Generate one assistant turn from a chat message list."""
    load_model(model_dir)
    assert _tokenizer is not None and _model is not None

    import torch

    prompt = _tokenizer.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=True
    )
    inputs = _tokenizer(prompt, return_tensors="pt").to(_model.device)

    with torch.no_grad():
        output_ids = _model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            do_sample=True,
            temperature=temperature,
            top_p=top_p,
        )

    new_tokens = output_ids[0][inputs["input_ids"].shape[1] :]
    return _tokenizer.decode(new_tokens, skip_special_tokens=True).strip()
