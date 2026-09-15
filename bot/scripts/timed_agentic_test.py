"""Drive a scripted multi-turn conversation through the running chat API and time
every turn, so we can measure the added latency of the agentic disposition path.

The script talks to the live FastAPI server (``uvicorn app.main:app`` on
``127.0.0.1:8001`` by default) over HTTP using only the standard library, so it
exercises the real generator backend (Vertex Gemini) and whatever
``TRI_BACK_DISPOSITION_MODE`` the server was started with.

For each turn it records wall-clock round-trip time and, when the turn reaches the
disposition step, the agent-trace status / step count returned in
``graph_traversal.agent_trace``. A per-turn table and summary stats are printed and
also written to ``data/latency_logs/<session_id>.json``.

Usage::

    python scripts/timed_agentic_test.py
    python scripts/timed_agentic_test.py --base-url http://127.0.0.1:8001
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]

# Scripted patient turns, ordered to satisfy the intake planner's slot priority
# (age -> sex -> anchor -> quality -> severity -> duration -> provocative ->
# palliative -> comorbidities) and to build a strong red-flag cluster
# (age > 50 + female + severe worsening night pain + cancer history + steroids +
# unexplained weight loss) that pushes the agentic path to reason over conditions.
_SCRIPTED_TURNS: list[str] = [
    "My lower back has been really hurting.",
    "I'm 68 years old.",
    "I'm a woman.",
    "My main problem is the pain in my lower back.",
    "It's a deep, boring, aching pain.",
    "It's about 9 out of 10.",
    "It started about three weeks ago and it keeps getting worse.",
    "Moving makes it much worse, and it's especially bad at night when I lie down.",
    "Honestly, nothing really seems to help it.",
    (
        "I have a history of breast cancer, I take prednisone daily, and I've "
        "lost about 10 pounds recently without trying."
    ),
]

# Sent if the bot is still asking questions after the scripted turns run out.
_FILLER_ANSWER = "No, there is nothing else I can think of to add."
_MAX_FILLER_TURNS = 4


def _post_chat(base_url: str, session_id: str, message: str, timeout: float) -> dict:
    payload = json.dumps({"session_id": session_id, "message": message}).encode("utf-8")
    req = urllib.request.Request(
        f"{base_url.rstrip('/')}/api/v1/chat",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _agent_trace_summary(resp: dict) -> dict | None:
    graph = resp.get("graph_traversal") or {}
    if not isinstance(graph, dict):
        return None
    trace = graph.get("agent_trace")
    if not isinstance(trace, dict):
        return None
    return {
        "status": trace.get("status"),
        "steps_taken": trace.get("steps_taken"),
        "max_steps": trace.get("max_steps"),
        "stop_reason": trace.get("stop_reason"),
        "available_tools": trace.get("available_tools"),
    }


def _truncate(text: str, limit: int = 240) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[: limit - 1] + "\u2026"


def run(base_url: str, timeout: float, *, tag: str = "") -> int:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    prefix = f"latency_test_{tag}_" if tag else "latency_test_"
    session_id = f"{prefix}{stamp}"
    print(f"=== Timed conversation test ===")
    print(f"base_url:   {base_url}")
    print(f"session_id: {session_id}")
    print(f"tag:        {tag or '(none)'}")
    print()

    turns: list[dict] = []
    scripted = list(_SCRIPTED_TURNS)
    filler_used = 0
    turn_index = 0

    while True:
        if scripted:
            message = scripted.pop(0)
        elif filler_used < _MAX_FILLER_TURNS:
            message = _FILLER_ANSWER
            filler_used += 1
        else:
            print("Reached filler cap without a disposition; stopping.")
            break

        turn_index += 1
        start = time.perf_counter()
        try:
            resp = _post_chat(base_url, session_id, message, timeout)
        except urllib.error.URLError as exc:
            print(f"[turn {turn_index}] request failed: {exc}")
            return 1
        elapsed = time.perf_counter() - start

        question_mode = bool(resp.get("question_mode"))
        agent = _agent_trace_summary(resp)
        record = {
            "turn": turn_index,
            "user_message": message,
            "elapsed_sec": round(elapsed, 3),
            "question_mode": question_mode,
            "coverage_ready": bool(resp.get("coverage_ready")),
            "escalated": bool(resp.get("escalated")),
            "agent_trace": agent,
            "response": resp.get("response", ""),
        }
        turns.append(record)

        phase = "QUESTION" if question_mode else "DISPOSITION"
        print(f"[turn {turn_index}] {elapsed:6.2f}s  {phase}")
        print(f"    user: {_truncate(message, 120)}")
        print(f"    bot:  {_truncate(record['response'])}")
        if agent:
            print(
                f"    agent_trace: status={agent['status']} "
                f"steps={agent['steps_taken']}/{agent['max_steps']} "
                f"stop={_truncate(str(agent.get('stop_reason')), 80)!r}"
            )
        print()

        if not question_mode:
            break

    _print_summary(turns)
    _write_log(session_id, base_url, turns)
    return 0


def _print_summary(turns: list[dict]) -> None:
    if not turns:
        print("No turns recorded.")
        return
    question_turns = [t for t in turns if t["question_mode"]]
    disposition_turns = [t for t in turns if not t["question_mode"]]

    print("=== Latency summary ===")
    print(f"{'turn':>4}  {'phase':<11}  {'seconds':>8}  agent")
    for t in turns:
        phase = "QUESTION" if t["question_mode"] else "DISPOSITION"
        agent = t["agent_trace"]
        agent_str = (
            f"{agent['status']} ({agent['steps_taken']}/{agent['max_steps']} steps)"
            if agent
            else "-"
        )
        print(f"{t['turn']:>4}  {phase:<11}  {t['elapsed_sec']:>8.2f}  {agent_str}")
    print()

    q_times = [t["elapsed_sec"] for t in question_turns]
    d_times = [t["elapsed_sec"] for t in disposition_turns]
    if q_times:
        print(
            f"Question turns  (n={len(q_times)}): "
            f"mean={statistics.mean(q_times):.2f}s  "
            f"median={statistics.median(q_times):.2f}s  "
            f"min={min(q_times):.2f}s  max={max(q_times):.2f}s"
        )
    if d_times:
        print(
            f"Disposition turn (n={len(d_times)}): "
            f"mean={statistics.mean(d_times):.2f}s  "
            f"max={max(d_times):.2f}s"
        )
    if q_times and d_times:
        delta = statistics.mean(d_times) - statistics.mean(q_times)
        print(
            f"Added agentic latency (disposition mean - question mean): {delta:+.2f}s"
        )
    print()


def _write_log(session_id: str, base_url: str, turns: list[dict]) -> None:
    log_dir = _ROOT / "data" / "latency_logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    out = log_dir / f"{session_id}.json"
    out.write_text(
        json.dumps(
            {
                "session_id": session_id,
                "base_url": base_url,
                "created_at": datetime.now().isoformat(),
                "turns": turns,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Wrote per-turn log to {out}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Timed agentic conversation test.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8001")
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument(
        "--tag",
        default="",
        help="Optional label embedded in the session_id / log filename "
        "(e.g. deterministic, agentic).",
    )
    args = parser.parse_args()
    return run(args.base_url, args.timeout, tag=args.tag.strip())


if __name__ == "__main__":
    raise SystemExit(main())
