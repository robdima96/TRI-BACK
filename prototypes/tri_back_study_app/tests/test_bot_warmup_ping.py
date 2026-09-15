"""Bot ready ping (login warmup)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from tri_back_study_app.adapters.http_client import ping_bot_ready


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
