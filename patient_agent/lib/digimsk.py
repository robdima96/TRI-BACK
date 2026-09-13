"""HTTP client for DigiMSKbot POST /api/v1/chat."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import urllib.error
import urllib.request
import json


@dataclass
class BotTurn:
    response: str
    question_mode: bool
    coverage_ready: bool
    escalated: bool
    raw: dict[str, Any]


class DigiMSKClient:
    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout: float = 120.0,
    ) -> None:
        self.base_url = (base_url or os.environ.get("DIGIMSK_BOT_URL") or "http://127.0.0.1:8001").rstrip("/")
        self.api_key = api_key if api_key is not None else os.environ.get("DIGIMSK_BOT_API_KEY")
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
                f"DigiMSK chat failed at {url}: {exc}. "
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
