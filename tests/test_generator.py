"""Generator backend selection and routing."""

from unittest.mock import patch

import pytest

from app.config import settings
from app.services.generator import (
    _generator_unavailable_stub,
    generate_from_messages,
    generator_model_configured,
    generator_status_detail,
)
from app.schemas import Evidence


@pytest.fixture
def vertex_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "generator_backend", "vertex")
    monkeypatch.setattr(settings, "generator_model", "gemini-2.0-flash-001")
    monkeypatch.setattr(settings, "vertex_project_id", "test-project")
    monkeypatch.setattr(settings, "vertex_location", "us-central1")
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)


@pytest.fixture(autouse=True)
def _vertex_adc_ok_for_tests(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "app.services.generator.vertex_adc_status",
        lambda: (True, "user ADC (test)"),
    )


def test_generator_configured_for_vertex(vertex_settings):
    assert generator_model_configured() is True
    assert "vertex" in generator_status_detail()


def test_generator_not_configured_for_vertex_without_project(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(settings, "generator_backend", "vertex")
    monkeypatch.setattr(settings, "vertex_project_id", None)
    assert generator_model_configured() is False


@patch("app.services.generator_backends.generate_vertex")
def test_generate_from_messages_routes_to_vertex(mock_vertex, vertex_settings):
    mock_vertex.return_value = "How long have you had the pain?"
    out = generate_from_messages(
        [{"role": "user", "content": "hello"}],
        max_new_tokens=64,
        temperature=0.2,
    )
    assert out == "How long have you had the pain?"
    mock_vertex.assert_called_once()


def test_generate_from_messages_rejects_unknown_backend(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "generator_backend", "legacy-remote")
    with pytest.raises(RuntimeError, match="unsupported DIGIMSK_GENERATOR_BACKEND"):
        generate_from_messages(
            [{"role": "user", "content": "hello"}],
            max_new_tokens=16,
            temperature=0.1,
        )


def test_generator_unavailable_stub_is_patient_facing_only():
    evidence = [
        Evidence(source="title: Example paper", snippet="snippet", score=0.9),
    ]
    text = _generator_unavailable_stub(
        "pain is 7/10",
        evidence,
        [{"role": "user", "content": "hello"}],
    )
    assert text == (
        "Please attend your nearest emergency department for "
        "appropriate clinical assessment."
    )
    assert "[source:" not in text
    assert "Query summary" not in text
    assert "prior turns" not in text
    assert "generator unavailable" not in text
