#!/usr/bin/env python3
"""Run 12-turn LBP vignette dialogues with a local Mistral instruct model.

For each scenario in LBPvignettes_conv.csv:
  1. Assistant greeting
  2–11. Five patient questions (q1–q5) and five assistant replies
  12. Final triage disposition

Usage::

    cd "Uncanny Valley"
    pip install -r requirements.txt
    python run_dialogues.py
    python run_dialogues.py --prompt system_prompt_2.txt
    python run_dialogues.py --scenario vignette_84
    python run_dialogues.py --dry-run
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from dialogue_runner import (
    init_run_context,
    run_scenario,
    write_final_bundle,
    write_scenario_text,
)
from llm_local import model_path_valid
from vignettes import load_scenarios

UV_DIR = Path(__file__).resolve().parent
DEFAULT_CSV = UV_DIR / "LBPvignettes_conv.csv"
DEFAULT_PROMPT = UV_DIR / "system_prompt_1.txt"
DEFAULT_MODEL = Path(r"E:\DigiMSKbot\Mistral7Binstruct")
DEFAULT_OUTPUT = UV_DIR / "output"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run vignette dialogues with a local LLM and system prompt file.",
    )
    parser.add_argument(
        "--csv",
        type=Path,
        default=DEFAULT_CSV,
        help=f"Vignette CSV (default: {DEFAULT_CSV.name})",
    )
    parser.add_argument(
        "--prompt",
        type=Path,
        default=DEFAULT_PROMPT,
        help="System prompt text file (default: system_prompt_1.txt)",
    )
    parser.add_argument(
        "--model-dir",
        type=Path,
        default=DEFAULT_MODEL,
        help=f"Local Hugging Face model directory (default: {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Directory for JSON and transcript outputs",
    )
    parser.add_argument(
        "--scenario",
        action="append",
        dest="scenarios",
        metavar="ID",
        help="Run only this scenario id (repeatable), e.g. vignette_84",
    )
    parser.add_argument(
        "--max-new-tokens",
        type=int,
        default=500,
        help="Max tokens per assistant generation",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate inputs and list scenarios without loading the model",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Debug logging",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(message)s",
    )

    if not args.csv.is_file():
        print(f"CSV not found: {args.csv}", file=sys.stderr)
        return 1
    if not args.prompt.is_file():
        print(f"Prompt file not found: {args.prompt}", file=sys.stderr)
        return 1

    system_prompt = args.prompt.read_text(encoding="utf-8").strip()
    if not system_prompt:
        print(f"Prompt file is empty: {args.prompt}", file=sys.stderr)
        return 1

    try:
        scenarios = load_scenarios(args.csv, sources=args.scenarios)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 1

    if not scenarios:
        print("No scenarios matched.", file=sys.stderr)
        return 1

    print(f"Prompt:  {args.prompt}")
    print(f"Model:   {args.model_dir}")
    print(f"CSV:     {args.csv}")
    print(f"Runs:    {len(scenarios)} scenario(s), 12 turns each")
    for s in scenarios:
        print(f"  - {s.source}")

    if args.dry_run:
        return 0

    if not model_path_valid(args.model_dir):
        print(
            f"Model weights not found at {args.model_dir}\n"
            "Set --model-dir to your local Mistral instruct folder.",
            file=sys.stderr,
        )
        return 1

    ctx = init_run_context(
        output_dir=args.output_dir,
        prompt_path=args.prompt,
        model_dir=args.model_dir,
        csv_path=args.csv,
    )
    print(f"Output:  {ctx.output_dir}")
    print(f"Run id:    {ctx.stamp}")

    dialogues = []
    for i, scenario in enumerate(scenarios, start=1):
        print(f"\n[{i}/{len(scenarios)}] Running {scenario.source} ...")
        dialogue = run_scenario(
            scenario,
            system_prompt,
            model_dir=args.model_dir,
            max_new_tokens=args.max_new_tokens,
        )
        dialogues.append(dialogue)
        txt_path = write_scenario_text(dialogue, ctx)
        print(f"  Done — {len(dialogue.turns)} turns. Wrote {txt_path.name}")

    json_path = write_final_bundle(dialogues, ctx)
    print(f"\nWrote bundle: {json_path}")
    print(f"Transcripts: {ctx.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
