"""Local launcher repairs a stale Reflex .web without touching Cloud Run."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_RUN_LOCAL = Path(__file__).resolve().parents[1] / "scripts" / "run_local.py"
_SPEC = importlib.util.spec_from_file_location("digimsk_run_local", _RUN_LOCAL)
assert _SPEC and _SPEC.loader
run_local = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(run_local)


def test_ensure_web_template_noop_when_complete(tmp_path: Path):
    template = tmp_path / "tpl"
    (template / "app").mkdir(parents=True)
    (template / "app" / "routes.js").write_text("from-template\n", encoding="utf-8")
    dest = tmp_path / ".web" / "app" / "routes.js"
    dest.parent.mkdir(parents=True)
    dest.write_text("existing\n", encoding="utf-8")
    assert run_local.ensure_web_template(tmp_path, template_dir=template) == "ok"
    assert dest.read_text(encoding="utf-8") == "existing\n"


def test_ensure_web_template_fills_missing_files(tmp_path: Path):
    template = tmp_path / "tpl"
    (template / "app").mkdir(parents=True)
    (template / "app" / "routes.js").write_text("routes\n", encoding="utf-8")
    (template / "components" / "reflex").mkdir(parents=True)
    provider = template / "components" / "reflex" / "radix_themes_color_mode_provider.js"
    provider.write_text("provider\n", encoding="utf-8")
    web_app = tmp_path / ".web" / "app"
    web_app.mkdir(parents=True)
    (web_app / "root.jsx").write_text("compiled\n", encoding="utf-8")
    assert run_local.ensure_web_template(tmp_path, template_dir=template) == "restored"
    assert (tmp_path / ".web" / "app" / "routes.js").read_text(encoding="utf-8") == "routes\n"
    assert (
        tmp_path / ".web" / "components" / "reflex" / "radix_themes_color_mode_provider.js"
    ).read_text(encoding="utf-8") == "provider\n"
    assert (web_app / "root.jsx").read_text(encoding="utf-8") == "compiled\n"


def test_ensure_web_template_leaves_absent_web_alone(tmp_path: Path):
    assert run_local.ensure_web_template(tmp_path) == "missing"
    assert not (tmp_path / ".web").exists()


def test_ensure_web_template_reinit_when_template_missing(tmp_path: Path):
    web = tmp_path / ".web"
    (web / "app").mkdir(parents=True)
    (web / "stale.txt").write_text("x", encoding="utf-8")
    missing = tmp_path / "no-such-template"
    assert run_local.ensure_web_template(tmp_path, template_dir=missing) == "reinit"
    assert not web.exists()


def test_reflex_run_args_pins_ports():
    assert run_local.reflex_run_args([]) == [
        "--frontend-port",
        "3000",
        "--backend-port",
        "8000",
    ]


def test_reflex_run_args_keeps_explicit_ports():
    extra = ["--frontend-port", "3005", "--backend-port", "8005"]
    assert run_local.reflex_run_args(extra) == extra


def test_port_is_busy_detects_bound_socket():
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        sock.listen(1)
        assert run_local.port_is_busy(port) is True
