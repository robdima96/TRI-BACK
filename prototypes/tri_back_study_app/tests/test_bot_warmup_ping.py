"""Bot ready ping (login warmup)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from tri_back_study_app.adapters.http_client import call_chat_api, ping_bot_ready


def test_ping_bot_ready_ok():
    resp = MagicMock()
    resp.status_code = 200
    resp.text = '{"status":"ready"}'
    client = AsyncMock()
    client.get = AsyncMock(return_value=resp)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)

    with patch("tri_back_study_app.adapters.http_client.httpx.AsyncClient", return_value=client):
        assert asyncio.run(ping_bot_ready()) is True
    client.get.assert_awaited()
    assert client.get.await_args.args[0].endswith("/ready")


def test_ping_bot_ready_swallows_errors():
    client = AsyncMock()
    client.get = AsyncMock(side_effect=RuntimeError("down"))
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)

    with patch("tri_back_study_app.adapters.http_client.httpx.AsyncClient", return_value=client):
        assert asyncio.run(ping_bot_ready()) is False


def test_call_chat_api_surfaces_error_detail():
    resp = MagicMock()
    resp.status_code = 503
    resp.json = MagicMock(return_value={"detail": "graph not ready: FactorSheetError: missing"})
    client = AsyncMock()
    client.post = AsyncMock(return_value=resp)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)

    with patch("tri_back_study_app.adapters.http_client.httpx.AsyncClient", return_value=client):
        try:
            asyncio.run(call_chat_api("admin_1", "I'm a 70 year old man"))
            raised = None
        except RuntimeError as exc:
            raised = str(exc)
    assert raised == "graph not ready: FactorSheetError: missing"
