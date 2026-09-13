#!/usr/bin/env python3
"""Launch the DigiMSK study UI locally.

Repairs a stale Reflex ``.web``, pins frontend :3000 / backend :8000 so the
WebSocket never lands on the bot (:8001), then starts the app.

Local-only: does not set DIGIMSK_PUBLIC_ACCESS or change Cloud Run entrypoints.

Usage (from repo root or this folder):

  python prototypes/digimsk_study_app/scripts/run_local.py --kill-stale
  python scripts/run_local.py --kill-stale
"""

from __future__ import annotations

import argparse
import os
import shutil
import socket
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTEND_PORT = 3000
BACKEND_PORT = 8000
BOT_PORT = 8001


def reflex_web_template_dir() -> Path | None:
    try:
        import reflex_base
    except ImportError:
        return None
    path = Path(reflex_base.__file__).resolve().parent / ".templates" / "web"
    return path if path.is_dir() else None


def ensure_web_template(
    root: Path,
    *,
    template_dir: Path | None = None,
) -> str:
    """Copy any missing Reflex web-template files into an existing ``.web``.

    Reflex 0.9 skips reinit when ``.web/reflex.json`` version matches, even if
    template files were deleted. Only fills gaps; never overwrites compiled
    pages. Returns ``ok``, ``restored``, ``reinit``, or ``missing``.
    """
    web = root / ".web"
    if not web.exists():
        return "missing"
    src = template_dir if template_dir is not None else reflex_web_template_dir()
    if src is None or not src.is_dir():
        shutil.rmtree(web)
        return "reinit"
    copied = 0
    for path in src.rglob("*"):
        if not path.is_file():
            continue
        dest = web / path.relative_to(src)
        if dest.exists():
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, dest)
        copied += 1
    return "restored" if copied else "ok"


def port_is_busy(port: int) -> bool:
    """True if something is already accepting on ``port`` or bind would fail."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.3)
        if probe.connect_ex(("127.0.0.1", port)) == 0:
            return True
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            if sys.platform != "win32":
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("", port))
    except OSError:
        return True
    return False


def pids_listening_on(port: int) -> list[int]:
    """Best-effort PIDs listening on ``port`` (Windows netstat / Unix lsof)."""
    pids: set[int] = set()
    try:
        if sys.platform == "win32":
            out = subprocess.check_output(
                ["netstat", "-ano", "-p", "tcp"],
                text=True,
                errors="replace",
            )
            for line in out.splitlines():
                if "LISTENING" not in line.upper():
                    continue
                parts = line.split()
                if len(parts) < 5:
                    continue
                _host, sep, port_s = parts[1].rpartition(":")
                if not sep or not port_s.isdigit() or int(port_s) != port:
                    continue
                pids.add(int(parts[-1]))
        else:
            out = subprocess.check_output(
                ["lsof", "-t", f"-iTCP:{port}", "-sTCP:LISTEN"],
                text=True,
                errors="replace",
            )
            for raw in out.split():
                pids.add(int(raw))
    except (subprocess.CalledProcessError, FileNotFoundError, ValueError):
        return []
    return sorted(p for p in pids if p > 0)


def kill_pids(pids: list[int]) -> None:
    for pid in pids:
        if pid == os.getpid():
            continue
        if sys.platform == "win32":
            subprocess.call(["taskkill", "/PID", str(pid), "/T", "/F"])
        else:
            subprocess.call(["kill", "-TERM", str(pid)])


def _has_flag(args: list[str], flag: str) -> bool:
    return flag in args or any(a.startswith(flag + "=") for a in args)


def reflex_run_args(extra: list[str]) -> list[str]:
    """Always pass explicit ports so Reflex will not auto-increment onto :8001."""
    args = list(extra)
    if not _has_flag(args, "--frontend-port"):
        args.extend(["--frontend-port", str(FRONTEND_PORT)])
    if not _has_flag(args, "--backend-port"):
        args.extend(["--backend-port", str(BACKEND_PORT)])
    return args


def _format_port_block(port: int, role: str) -> str:
    pids = pids_listening_on(port)
    pid_txt = ", ".join(str(p) for p in pids) if pids else "unknown PID"
    kill = ""
    if pids:
        if sys.platform == "win32":
            kill = "  " + " ; ".join(f"taskkill /PID {p} /T /F" for p in pids) + "\n"
        else:
            kill = "  " + " ".join(["kill", "-TERM", *map(str, pids)]) + "\n"
    return (
        f"Port {port} ({role}) is already in use ({pid_txt}).\n"
        f"Reflex WebSocket must stay on {BACKEND_PORT}; the bot uses {BOT_PORT}.\n"
        f"{kill}"
        f"Or re-run: python scripts/run_local.py --kill-stale\n"
    )


def ensure_local_ports(*, kill_stale: bool) -> int:
    """Keep :3000 / :8000 free. Return 0, or 1 if the user must free a port."""
    busy = [
        (port, role)
        for port, role in (
            (FRONTEND_PORT, "study UI"),
            (BACKEND_PORT, "Reflex WebSocket backend"),
        )
        if port_is_busy(port)
    ]
    if not busy:
        return 0
    if kill_stale:
        for port, role in busy:
            pids = pids_listening_on(port)
            print(f"Killing leftover process on {port} ({role}): {pids or 'PID unknown'}", flush=True)
            kill_pids(pids)
        still = [port for port, _role in busy if port_is_busy(port)]
        if still:
            print(
                "Could not free ports "
                + ", ".join(str(p) for p in still)
                + ". Close the other terminal using them and retry.",
                file=sys.stderr,
                flush=True,
            )
            return 1
        return 0
    for port, role in busy:
        print(_format_port_block(port, role), file=sys.stderr, flush=True)
    return 1


def _venv_python(root: Path) -> Path:
    scripts = root / ".venv" / ("Scripts" if sys.platform == "win32" else "bin")
    return scripts / ("python.exe" if sys.platform == "win32" else "python")


def _ensure_venv(root: Path) -> Path:
    python = _venv_python(root)
    req = root / "requirements.txt"
    if not python.is_file():
        print("Creating local venv and installing requirements...", flush=True)
        subprocess.check_call([sys.executable, "-m", "venv", str(root / ".venv")])
        subprocess.check_call(
            [str(python), "-m", "pip", "install", "-r", str(req)],
            cwd=root,
        )
    return python


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Launch the local DigiMSK study UI")
    parser.add_argument(
        "--kill-stale",
        action="store_true",
        help=f"Kill leftover processes on {FRONTEND_PORT}/{BACKEND_PORT} before start",
    )
    args, extra = parser.parse_known_args(sys.argv[1:] if argv is None else argv)

    os.chdir(ROOT)
    python = _ensure_venv(ROOT)
    action = ensure_web_template(ROOT)
    if action == "restored":
        print("Restored missing Reflex template files in .web.", flush=True)
    elif action == "reinit":
        print("Removed incomplete .web so Reflex can reinitialize it.", flush=True)
    elif action == "missing":
        print("No .web yet; Reflex will create it on first run.", flush=True)

    if ensure_local_ports(kill_stale=args.kill_stale) != 0:
        return 1

    if not port_is_busy(BOT_PORT):
        print(
            f"Warning: nothing is listening on {BOT_PORT}. "
            "Start the bot first: cd bot; uvicorn app.main:app --reload --host 127.0.0.1 --port 8001",
            flush=True,
        )

    reflex_cmd = [str(python), "-m", "reflex", "run", *reflex_run_args(extra)]
    print(f"Starting study UI at http://localhost:{FRONTEND_PORT}", flush=True)
    print(f"Reflex WebSocket backend: http://127.0.0.1:{BACKEND_PORT}", flush=True)
    print(f"Bot API should already be on http://127.0.0.1:{BOT_PORT}", flush=True)
    return subprocess.call(reflex_cmd, cwd=ROOT)


if __name__ == "__main__":
    raise SystemExit(main())
