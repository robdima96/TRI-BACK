"""Grounded patient agent: AgentClinic card + CRAFT-MD disclosure rules."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Protocol

from lib.cards import patient_actor_only
from lib.vertex_config import vertex_runtime

_PROMPT_PATH = Path(__file__).resolve().parents[1] / "references" / "patient_prompt_draft.txt"

_CHARACTER_BREAK = re.compile(
    r"\b(as an ai|language model|vignette|paragraph provided|patient_actor|case card)\b",
    re.I,
)
_JARGON = re.compile(
    r"\b(radiculopathy|cauda equina|saddle anesthesia|lumbosacral|osteoporotic|"
    r"spondylolisthesis|discitis|epidural abscess)\b",
    re.I,
)


class LLMBackend(Protocol):
    def complete(self, system: str, user: str) -> str: ...


class EchoBackend:
    """Deterministic backend for tests and dry-runs. Does not invent facts."""

    def __init__(self, actor: dict[str, Any]) -> None:
        self.actor = actor

    def complete(self, system: str, user: str) -> str:
        if "(none yet)" in user:
            return str(self.actor.get("opening_complaint") or "My back hurts.")
        return "I'm not sure — nobody's told me that."


class OpenAIBackend:
    def __init__(self, model: str, temperature: float = 0.05) -> None:
        self.model = model
        self.temperature = temperature

    def complete(self, system: str, user: str) -> str:
        from openai import OpenAI

        client = OpenAI()
        resp = client.chat.completions.create(
            model=self.model,
            temperature=self.temperature,
            max_tokens=120,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return (resp.choices[0].message.content or "").strip()


class VertexBackend:
    """Gemini on Vertex AI — same project, location, ADC, and default model as DigiMSK generator."""

    def __init__(
        self,
        *,
        model: str | None = None,
        temperature: float = 0.05,
        max_output_tokens: int = 120,
    ) -> None:
        self.runtime = vertex_runtime(cli_model=model)
        self.model = self.runtime.model
        self.temperature = temperature
        self.max_output_tokens = max_output_tokens
        self._initialized = False

    def _ensure(self) -> None:
        if self._initialized:
            return
        try:
            import vertexai
        except ImportError as exc:
            raise RuntimeError(
                "google-cloud-aiplatform is required for --backend vertex "
                "(pip install google-cloud-aiplatform)"
            ) from exc
        vertexai.init(project=self.runtime.project_id, location=self.runtime.location)
        self._initialized = True

    def complete(self, system: str, user: str) -> str:
        self._ensure()
        from vertexai.generative_models import GenerationConfig, GenerativeModel

        model = GenerativeModel(self.model, system_instruction=system)
        response = model.generate_content(
            user,
            generation_config=GenerationConfig(
                max_output_tokens=self.max_output_tokens,
                temperature=self.temperature,
                top_p=0.9,
            ),
        )
        text = getattr(response, "text", None)
        if text:
            return text.strip()
        raise RuntimeError(f"Vertex returned no text (model={self.model})")


class LocalMistralBackend:
    """Optional local instruct model (same family as Uncanny Valley)."""

    def __init__(self, model_dir: str, temperature: float = 0.05) -> None:
        self.model_dir = model_dir
        self.temperature = temperature

    def complete(self, system: str, user: str) -> str:
        uv_root = Path(__file__).resolve().parents[2] / "Uncanny Valley"
        import sys

        if str(uv_root) not in sys.path:
            sys.path.insert(0, str(uv_root))
        try:
            from llm_local import generate_reply
        except ImportError as exc:
            raise RuntimeError(
                "Local backend needs Uncanny Valley/llm_local.py and transformers. "
                "Use --backend echo until the patient model is decided."
            ) from exc
        return generate_reply(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            model_dir=self.model_dir,
            max_new_tokens=80,
            temperature=self.temperature,
        )


def load_system_prompt(actor: dict[str, Any]) -> str:
    template = _PROMPT_PATH.read_text(encoding="utf-8")
    blob = json.dumps(actor, indent=2, ensure_ascii=False)
    if "{json.dumps(Patient_Actor)}" in template:
        template = template.replace("{json.dumps(Patient_Actor)}", blob)
    # Keep only the system half (before TURN PROMPT).
    if "TURN PROMPT" in template:
        template = template.split("TURN PROMPT")[0]
    return template.strip()


def turn_user_prompt(history: str, bot_message: str) -> str:
    return (
        "Here is the conversation so far:\n"
        f"{history or '(none yet)'}\n\n"
        "The chatbot just said:\n"
        f"{bot_message}\n\n"
        "Reply as the patient. Patient:"
    )


REMOVED_HIDDEN_KEYS = (
    "objective_for_bot",
    "physical_exam_if_any",
    "test_results_if_any",
    "correct_diagnosis",
)


class PatientAgent:
    def __init__(self, card: dict[str, Any], backend: LLMBackend) -> None:
        self.card = card
        self.actor = patient_actor_only(card)
        self.backend = backend
        hidden = card.get("Hidden") or {}
        actor_blob = json.dumps(self.actor)
        for key in REMOVED_HIDDEN_KEYS:
            if key in hidden:
                raise ValueError(f"removed Hidden field {key!r} must not be on the OSCE card")
            if key in actor_blob:
                raise ValueError(f"{key} must not appear on Patient_Actor")
        self.system = load_system_prompt(self.actor)
        self.history_lines: list[str] = []

    def opening(self) -> str:
        text = str(self.actor.get("opening_complaint") or "My back hurts.")
        self.history_lines.append(f"Patient: {text}")
        return text

    def reply(self, bot_message: str) -> str:
        self.history_lines.append(f"Chatbot: {bot_message}")
        user = turn_user_prompt("\n".join(self.history_lines), bot_message)
        text = self.backend.complete(self.system, user).strip()
        text = _strip_role_prefix(text)
        self.history_lines.append(f"Patient: {text}")
        return text

    def transcript(self) -> list[str]:
        return list(self.history_lines)


def _strip_role_prefix(text: str) -> str:
    return re.sub(r"^(patient|user)\s*:\s*", "", text.strip(), flags=re.I)


def flag_reply(text: str) -> list[str]:
    flags = []
    if _CHARACTER_BREAK.search(text):
        flags.append("character_break")
    if _JARGON.search(text):
        flags.append("jargon")
    return flags


def make_backend(kind: str, actor: dict[str, Any], *, model: str | None = None) -> LLMBackend:
    if kind in {"echo", "dry-run", "dry_run"}:
        return EchoBackend(actor)
    if kind in {"vertex", "gemini", "google", "gcp"}:
        return VertexBackend(model=model)
    if kind in {"openai", "openai_compat"}:
        model = model or os.environ.get("PATIENT_MODEL", "gpt-4o-mini")
        return OpenAIBackend(model=model)
    if kind in {"local", "mistral"}:
        model_dir = model or os.environ.get("PATIENT_MODEL_DIR") or r"E:\DigiMSKbot\Mistral7Binstruct"
        return LocalMistralBackend(model_dir=model_dir)
    raise ValueError(f"unknown backend {kind!r}; use vertex, echo, openai, or local")
