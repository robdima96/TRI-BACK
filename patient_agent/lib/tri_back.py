"""HTTP client for TRI-BACK POST /api/v1/chat."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


def _env_lookup(name: str) -> str:
    if name.startswith("TRI_BACK_"):
        keys = (name, "TRI_BACK_" + name[len("TRI_BACK_") :])
    elif name.startswith("TRI_BACK_"):
        keys = ("TRI_BACK_" + name[len("TRI_BACK_") :], name)
    else:
        keys = (name,)
    for key in keys:
        val = (os.environ.get(key) or "").strip()
        if val:
            return val
    return ""


@dataclass
class BotTurn:
    response: str
    question_mode: bool
    coverage_ready: bool
    escalated: bool
    raw: dict[str, Any]


class TriBackClient:
    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout: float = 120.0,
    ) -> None:
        self.base_url = (
            base_url or _env_lookup("TRI_BACK_BOT_URL") or "http://127.0.0.1:8001"
        ).rstrip("/")
        if api_key is not None:
            self.api_key = api_key
        else:
            self.api_key = _env_lookup("TRI_BACK_BOT_API_KEY") or None
        self.timeout = timeout

    def chat(self, session_id: str, message: str) -> BotTurn:
        url = f"{self.base_url}/api/v1/chat"
        payload = json.dumps({"session_id": session_id, "message": message}).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise RuntimeError(
                f"TRI-BACK chat failed at {url}: {exc}. "
                "Start the bot on port 8001 (usual local URL http://127.0.0.1:8001)."
            ) from exc
        return BotTurn(
            response=str(body.get("response") or ""),
            question_mode=bool(body.get("question_mode")),
            coverage_ready=bool(body.get("coverage_ready")),
            escalated=bool(body.get("escalated")),
            raw=body,
        )

    def should_stop(self, turn: BotTurn) -> bool:
        if turn.escalated:
            return True
        if turn.coverage_ready:
            return True
        if not turn.question_mode and turn.response:
            return True
        return False


