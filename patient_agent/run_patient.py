"""CLI: run a grounded patient agent against TRI-BACK (or echo dry-run).

  python run_patient.py --card PATH --backend echo
  python run_patient.py --card PATH --backend vertex --bot-url http://127.0.0.1:8001
  python run_patient.py --card PATH --backend vertex --model gemini-2.0-flash
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib.cards import load_card, patient_actor_only
from lib.tri_back import TriBackClient
from lib.gates import summarize_flags
from lib.patient import PatientAgent, VertexBackend, make_backend


def main() -> int:
    parser = argparse.ArgumentParser(description="Dialogue between patient agent and TRI-BACK.")
    parser.add_argument("--card", type=Path, required=True)
    parser.add_argument(
        "--backend",
        choices=("vertex", "echo", "openai", "local"),
        default="vertex",
        help="vertex = same GCP/Vertex auth as TRI-BACK generator (default)",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Vertex model id (overrides PATIENT_VERTEX_MODEL and TRI_BACK_GENERATOR_MODEL)",
    )
    parser.add_argument("--bot-url", default=None, help="Default http://127.0.0.1:8001")
    parser.add_argument("--max-turns", type=int, default=20)
    parser.add_argument("--session-id", default=None)
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Transcript JSON path (default outputs/dialogues/<session>.json)",
    )
    args = parser.parse_args()

    card = load_card(args.card)
    actor = patient_actor_only(card)
    backend = make_backend(args.backend, actor, model=args.model)
    agent = PatientAgent(card, backend)

    model_meta: dict = {"backend": args.backend}
    if isinstance(backend, VertexBackend):
        model_meta.update(
            {
                "vertex_model": backend.model,
                "vertex_model_source": backend.runtime.model_source,
                "vertex_project": backend.runtime.project_id,
                "vertex_location": backend.runtime.location,
            }
        )
        print(
            json.dumps(
                {
                    "vertex": {
                        "model": backend.model,
                        "source": backend.runtime.model_source,
                        "project": backend.runtime.project_id,
                        "location": backend.runtime.location,
                    }
                }
            ),
            file=sys.stderr,
        )

    session_id = args.session_id or f"pa_{uuid.uuid4().hex[:12]}"
    patient_turns: list[str] = []
    log: list[dict] = []

    opening = agent.opening()
    patient_turns.append(opening)
    log.append({"role": "patient", "text": opening, "flags": []})

    if args.backend == "echo":
        fake = "How long has this been going on?"
        reply = agent.reply(fake)
        patient_turns.append(reply)
        log.append({"role": "chatbot", "text": fake, "question_mode": True})
        log.append({"role": "patient", "text": reply})
    else:
        client = TriBackClient(base_url=args.bot_url)
        bot = client.chat(session_id, opening)
        log.append(
            {
                "role": "chatbot",
                "text": bot.response,
                "question_mode": bot.question_mode,
                "coverage_ready": bot.coverage_ready,
                "escalated": bot.escalated,
            }
        )
        turns = 1
        while turns < args.max_turns and not client.should_stop(bot):
            reply = agent.reply(bot.response)
            patient_turns.append(reply)
            log.append({"role": "patient", "text": reply})
            bot = client.chat(session_id, reply)
            log.append(
                {
                    "role": "chatbot",
                    "text": bot.response,
                    "question_mode": bot.question_mode,
                    "coverage_ready": bot.coverage_ready,
                    "escalated": bot.escalated,
                }
            )
            turns += 1

    gates = summarize_flags(patient_turns, card)
    out = args.out or (ROOT / "outputs" / "dialogues" / f"{session_id}.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "session_id": session_id,
        "case_id": card.get("case_id"),
        "source_id": card.get("source_id"),
        "card_path": str(args.card),
        "bot_url": args.bot_url or "http://127.0.0.1:8001",
        **model_meta,
        "messages": log,
        "gates": gates,
    }
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"wrote": str(out), "gates": gates}, indent=2))
    return 0 if gates["pass"] or args.backend == "echo" else 1


if __name__ == "__main__":
    raise SystemExit(main())
