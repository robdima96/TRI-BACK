"""Run 12-turn vignette dialogues against a local LLM."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from llm_local import generate_reply
from vignettes import Scenario

_log = logging.getLogger(__name__)

GREETING_TRIGGER = (
    "A new patient is starting a chat session about musculoskeletal symptoms. "
    "Provide your opening greeting: welcome them briefly and invite them to "
    "describe what brings them in. Keep it concise (2–4 sentences)."
)

DISPOSITION_TRIGGER = (
    "Based on everything the patient has told you in this conversation, "
    "provide your final triage disposition and care recommendation. "
    "State the recommended level of care and urgency clearly "
    "(for example: emergency department now, see a doctor within hours or days, "
    "pharmacy or self-care with precautions, or seek care if symptoms worsen). "
    "Do not give a formal diagnosis."
)


@dataclass
class Turn:
    turn: int
    role: str
    phase: str
    content: str


@dataclass
class DialogueResult:
    source: str
    ada_disposition_reference: str
    turns: list[Turn] = field(default_factory=list)


def _chat_history(turns: list[Turn]) -> list[dict[str, str]]:
    return [{"role": t.role, "content": t.content} for t in turns]


def _build_messages(
    system_prompt: str,
    history: list[Turn],
    user_message: str | None,
) -> list[dict[str, str]]:
    """Assemble messages for apply_chat_template (roles must alternate after system)."""
    messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
    chat = _chat_history(history)

    if chat and chat[0]["role"] == "assistant":
        chat.insert(0, {"role": "user", "content": GREETING_TRIGGER})

    messages.extend(chat)

    if user_message is not None:
        if not chat or chat[-1].get("content") != user_message:
            messages.append({"role": "user", "content": user_message})

    return messages


def _generate(
    system_prompt: str,
    history: list[Turn],
    user_message: str | None,
    *,
    model_dir: Path,
    max_new_tokens: int,
) -> str:
    messages = _build_messages(system_prompt, history, user_message)
    return generate_reply(
        messages,
        model_dir=model_dir,
        max_new_tokens=max_new_tokens,
    )


def run_scenario(
    scenario: Scenario,
    system_prompt: str,
    *,
    model_dir: Path,
    max_new_tokens: int,
) -> DialogueResult:
    result = DialogueResult(
        source=scenario.source,
        ada_disposition_reference=scenario.ada_disposition,
    )
    history: list[Turn] = []
    turn_num = 0

    def add_turn(role: str, phase: str, content: str) -> None:
        nonlocal turn_num
        turn_num += 1
        history.append(Turn(turn=turn_num, role=role, phase=phase, content=content))
        result.turns.append(history[-1])

    _log.info("Scenario %s — generating greeting", scenario.source)
    greeting = _generate(
        system_prompt,
        history,
        GREETING_TRIGGER,
        model_dir=model_dir,
        max_new_tokens=max_new_tokens,
    )
    add_turn("assistant", "greeting", greeting)

    for i, patient_msg in enumerate(scenario.patient_turns, start=1):
        _log.info("Scenario %s — patient q%d", scenario.source, i)
        add_turn("user", f"patient_q{i}", patient_msg)

        _log.info("Scenario %s — assistant response q%d", scenario.source, i)
        reply = _generate(
            system_prompt,
            history,
            user_message=None,
            model_dir=model_dir,
            max_new_tokens=max_new_tokens,
        )
        add_turn("assistant", f"assistant_q{i}", reply)

    _log.info("Scenario %s — generating disposition", scenario.source)
    disposition = _generate(
        system_prompt,
        history,
        DISPOSITION_TRIGGER,
        model_dir=model_dir,
        max_new_tokens=max_new_tokens,
    )
    add_turn("assistant", "disposition", disposition)

    return result


@dataclass(frozen=True)
class RunContext:
    """Shared metadata for one invocation of run_dialogues.py."""

    stamp: str
    prompt_stem: str
    output_dir: Path
    prompt_path: Path
    model_dir: Path
    csv_path: Path


def init_run_context(
    *,
    output_dir: Path,
    prompt_path: Path,
    model_dir: Path,
    csv_path: Path,
) -> RunContext:
    output_dir.mkdir(parents=True, exist_ok=True)
    return RunContext(
        stamp=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ"),
        prompt_stem=prompt_path.stem,
        output_dir=output_dir,
        prompt_path=prompt_path,
        model_dir=model_dir,
        csv_path=csv_path,
    )


def scenario_text_path(dialogue: DialogueResult, ctx: RunContext) -> Path:
    return ctx.output_dir / f"{dialogue.source}_{ctx.prompt_stem}_{ctx.stamp}.txt"


def write_scenario_text(dialogue: DialogueResult, ctx: RunContext) -> Path:
    """Write one scenario transcript immediately after it completes."""
    path = scenario_text_path(dialogue, ctx)
    path.write_text(format_transcript(dialogue), encoding="utf-8")
    _log.info("Wrote transcript %s", path.name)
    return path


def format_transcript(dialogue: DialogueResult) -> str:
    lines = [
        f"Scenario: {dialogue.source}",
        f"Reference disposition (Ada): {dialogue.ada_disposition_reference}",
        f"Turns: {len(dialogue.turns)}",
        "",
    ]
    for t in dialogue.turns:
        label = t.phase.replace("_", " ").title()
        speaker = "Assistant" if t.role == "assistant" else "Patient"
        lines.append(f"--- Turn {t.turn} [{label}] {speaker} ---")
        lines.append(t.content)
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_final_bundle(dialogues: list[DialogueResult], ctx: RunContext) -> Path:
    """Write combined JSON bundle and summary after all scenarios finish."""
    bundle = {
        "generated_at": ctx.stamp,
        "prompt_file": str(ctx.prompt_path),
        "model_dir": str(ctx.model_dir),
        "csv_file": str(ctx.csv_path),
        "scenario_count": len(dialogues),
        "turns_per_scenario": 12,
        "scenarios": [
            {
                "source": d.source,
                "ada_disposition_reference": d.ada_disposition_reference,
                "turns": [asdict(t) for t in d.turns],
            }
            for d in dialogues
        ],
    }

    json_path = ctx.output_dir / f"dialogues_{ctx.prompt_stem}_{ctx.stamp}.json"
    json_path.write_text(json.dumps(bundle, indent=2, ensure_ascii=False), encoding="utf-8")

    summary_path = ctx.output_dir / f"SUMMARY_{ctx.prompt_stem}_{ctx.stamp}.txt"
    summary_path.write_text(
        "\n".join(
            [
                f"Prompt: {ctx.prompt_path}",
                f"Model: {ctx.model_dir}",
                f"CSV: {ctx.csv_path}",
                f"Scenarios: {len(dialogues)}",
                f"JSON: {json_path.name}",
                "",
                "Per-scenario transcripts (written after each scenario):",
                *[f"  - {scenario_text_path(d, ctx).name}" for d in dialogues],
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    return json_path


def write_outputs(
    dialogues: list[DialogueResult],
    *,
    output_dir: Path,
    prompt_path: Path,
    model_dir: Path,
    csv_path: Path,
) -> Path:
    """Backward-compatible wrapper: writes any missing text files + final bundle."""
    ctx = init_run_context(
        output_dir=output_dir,
        prompt_path=prompt_path,
        model_dir=model_dir,
        csv_path=csv_path,
    )
    for dialogue in dialogues:
        path = scenario_text_path(dialogue, ctx)
        if not path.is_file():
            write_scenario_text(dialogue, ctx)
    return write_final_bundle(dialogues, ctx)
