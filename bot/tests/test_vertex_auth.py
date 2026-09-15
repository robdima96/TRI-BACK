"""Vertex Application Default Credentials checks."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.services.vertex_auth import vertex_adc_status


def test_vertex_adc_rejects_service_account_key_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", r"C:\secrets\key.json")
    monkeypatch.delenv("K_SERVICE", raising=False)
    ok, detail = vertex_adc_status()
    assert ok is False
    assert "GOOGLE_APPLICATION_CREDENTIALS" in detail


def test_vertex_adc_missing_when_no_adc_and_default_fails(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    monkeypatch.delenv("K_SERVICE", raising=False)
    with patch("app.services.vertex_auth._adc_file_path", return_value=None):
        with patch("google.auth.default", side_effect=Exception("no creds")):
            ok, detail = vertex_adc_status()
    assert ok is False
    assert "application-default login" in detail


def test_vertex_adc_ok_when_credentials_load(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    monkeypatch.delenv("K_SERVICE", raising=False)
    fake_adc = Path("C:/Users/me/AppData/Roaming/gcloud/application_default_credentials.json")
    mock_creds = MagicMock()
    with patch("app.services.vertex_auth._adc_file_path", return_value=fake_adc):
        with patch.object(Path, "is_file", return_value=True):
            with patch("google.auth.default", return_value=(mock_creds, "my-project")):
                ok, detail = vertex_adc_status()
    assert ok is True
    assert "user ADC" in detail
    assert "my-project" in detail


def test_vertex_adc_ok_on_cloud_run_metadata(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    monkeypatch.setenv("K_SERVICE", "tri-back")
    mock_creds = MagicMock()
    with patch("app.services.vertex_auth._adc_file_path", return_value=None):
        with patch("google.auth.default", return_value=(mock_creds, "project-x")):
            ok, detail = vertex_adc_status()
    assert ok is True
    assert "Cloud Run" in detail
