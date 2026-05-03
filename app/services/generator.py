"""Draft responses via local Mistral-style causal LM."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from app.config import settings
from app.schemas import Evidence

_log = logging.getLogger(__name__)

_tok_gen: Any = None # tokenizer
_mdl_gen: Any = None # model

# define chatbot role, constraints, and behavior
# optionally add ReACT and/or example query and response
_SYSTEM_INSTRUCTION = (
    "You are a helpful and conservative musculoskeletal health information assistant. "
    "Base your answer ONLY on the Evidence provided. "
    "If the evidence does not cover the question, say you don't have enough information. "
    "Never diagnose. Never prescribe. Always recommend consulting a qualified clinician. "
    "For all queries, keep in mind that your role is to support the individual's "
    "capacity to cope with life autonomously- not to provide a diagnosis or treatment. "
    "When answering questions, think through the problem step by step before giving "
    "your final answer. "
)


def _generator_path_looks_valid(generator_dir: str) -> bool:
    root = Path(generator_dir)
    if not root.is_dir():
        return False
    return any(root.glob("*.safetensors")) or (root / "model.safetensors").is_file()


def generator_model_configured() -> bool:
    """True when local weight files exist (does not load the model)."""
    return _generator_path_looks_valid(settings.generator_model_dir)


_LOCAL_GENERATE = _generator_path_looks_valid(settings.generator_model_dir)


# checks that safetensor LLM files are available
def _ensure_generator(generator_dir: str) -> bool: 
    global _tok_gen, _mdl_gen
    if _mdl_gen is not None and _tok_gen is not None:
        return True
    root = Path(generator_dir)
    if not root.is_dir():
        return False
    st = any(root.glob("*.safetensors")) or (root / "model.safetensors").is_file()
    if not st:
        return False
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    p = str(root.resolve())
    _tok_gen = AutoTokenizer.from_pretrained(p, local_files_only=True) # no network downloads
    _mdl_gen = AutoModelForCausalLM.from_pretrained(
        p,
        torch_dtype=torch.float16,
        device_map="auto", # HF accelerator handles device allocation internally
    )
    return True

# assembles conversation context for chat generation
# 1. conversation history
# 2. system instruction 
# 3. evidence
# 4. current user message
def _build_messages_for_chat(
    query: str,
    evidence: list[dict[str, Any]],
    conversation_history: list[dict[str, str]] | None,
) -> list[dict[str, str]]:
    # converts list[Evidence] to formatted citation block
    lines = [f"- [{e.get('source', '')}] \"{e.get('snippet', '')}\"" for e in evidence]
    block = "\n".join(lines) if lines else "No evidence available."
    current_content = (
        f"{_SYSTEM_INSTRUCTION}\n\n"
        f"Evidence:\n{block}\n\n"
        f"Current user message: {query}"
    )
    messages: list[dict[str, str]] = []
    for turn in conversation_history or []:
        role = turn.get("role", "user")
        content = turn.get("content", "")
        if role not in ("user", "assistant"): # handles missing or invalid roles
            role = "user"
        messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": current_content})
    return messages


# LLM inference function
def _forward_generate(
    query: str,
    evidence: list[Evidence],
    generator_dir: str,
    *,
    conversation_history: list[dict[str, str]] | None = None,
) -> str:
    # converts list[Evidence] to plain Python dicts for _build_messages_for_chat()
    ev: list[dict[str, Any]] = [e.model_dump() for e in evidence]
    # fallback if generator model is not available
    if not _ensure_generator(generator_dir):
        return (
            "Please attend your nearest emergency department for "
            "appropriate clinical assessment (generator unavailable locally)."
        )
    import torch

    assert _tok_gen is not None and _mdl_gen is not None
    messages = _build_messages_for_chat(query, ev, conversation_history)
    prompt = _tok_gen.apply_chat_template( # converts messages to prompt string for Mistral-style causal LM
        messages, tokenize=False, add_generation_prompt=True
    )
    # converts prompt to PyTorch tensors and moves to appropriate device
    inputs = _tok_gen(prompt, return_tensors="pt").to(_mdl_gen.device) 

    with torch.no_grad(): # no gradient computation, faster inference
        output_ids = _mdl_gen.generate(
            **inputs,
            max_new_tokens=500, # hard cap on response length
            do_sample=True, # probability-based sampling
            temperature=0.2, # keep low to reduce hallucinations
            top_p=0.9, # nucleus sampling- only considers top-p probability mass
        )
    # remove prompt tokens from output    
    new_tokens = output_ids[0][inputs["input_ids"].shape[1] :] # extracts generated tokens from output
    # converts tokens to text and removes special tokens
    return _tok_gen.decode(new_tokens, skip_special_tokens=True).strip()

# public interface for generating responses
# skips generator if not available
def generate_response(
    query: str,
    evidence: list[Evidence],
    *,
    conversation_history: list[dict[str, str]] | None = None,
) -> str:
    """Generate a draft with the local language model, or a stub when it is unavailable."""
    if _LOCAL_GENERATE:
        try:
            return _forward_generate(
                query,
                evidence,
                settings.generator_model_dir,
                conversation_history=conversation_history,
            )
        except Exception as e:
            _log.exception("local generate failed: %s", e)

    source_label = evidence[0].source if evidence else "no-source"
    hist_note = ""
    if conversation_history:
        hist_note = f" [prior turns: {len(conversation_history)}]"
    return (
        "Please attend your nearest emergency department for "
        "appropriate clinical assessment (generator unavailable locally)."
        f"[source: {source_label}] Query summary: {query[:120]}{hist_note}"
    )
