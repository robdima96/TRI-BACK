"""Cloud Run identity token + API key header layout."""

from __future__ import annotations

from unittest.mock import patch

from tri_back_study_app.adapters.http_client import bot_headers


def test_local_api_key_only():
    with patch(
        "tri_back_study_app.adapters.http_client.fetch_cloud_run_identity_token",
        return_value=None,
    ):
        headers = bot_headers(api_key="secret", base_url="http://127.0.0.1:8001")
    assert headers == {"Authorization": "Bearer secret"}


def test_hosted_api_key_plus_identity():
    with patch(
        "tri_back_study_app.adapters.http_client.fetch_cloud_run_identity_token",
        return_value="ya29.id-token",
    ) as fetch:
        headers = bot_headers(
            api_key="secret",
            base_url="https://tri-back-PLACEHOLDER-uc.a.run.app",
        )
    fetch.assert_called_once()
    assert headers["Authorization"] == "Bearer secret"
    assert headers["X-Serverless-Authorization"] == "Bearer ya29.id-token"


def test_hosted_identity_only_when_no_api_key():
    with patch(
        "tri_back_study_app.adapters.http_client.fetch_cloud_run_identity_token",
        return_value="ya29.id-token",
    ):
        headers = bot_headers(
            api_key="",
            base_url="https://tri-back-PLACEHOLDER-uc.a.run.app",
        )
    assert headers == {"Authorization": "Bearer ya29.id-token"}
