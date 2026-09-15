"""Generator backend selection and routing."""

from unittest.mock import MagicMock, patch

import pytest

from app.config import settings
from app.services.generator import (
    _generator_unavailable_stub,
    generate_from_messages,
    generator_model_configured,
    generator_status_detail,
)
from app.services.generator_backends import GenerationEmptyError, _extract_response_text
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
    with pytest.raises(RuntimeError, match="unsupported TRI_BACK_GENERATOR_BACKEND"):
        generate_from_messages(
            [{"role": "user", "content": "hello"}],
            max_new_tokens=16,
            temperature=0.1,
        )


def test_generator_unavailable_stub_is_non_clinical_system_failure():
    from app.services.generator import GENERATOR_SYSTEM_FAILURE_TEXT

    evidence = [
        Evidence(source="title: Example paper", snippet="snippet", score=0.9),
    ]
    text = _generator_unavailable_stub(
        "pain is 7/10",
        evidence,
        [{"role": "user", "content": "hello"}],
    )
    assert text == GENERATOR_SYSTEM_FAILURE_TEXT
    assert "emergency department" not in text.lower()
    assert "[source:" not in text
    assert "Query summary" not in text
    assert "prior turns" not in text
    assert "generator unavailable" not in text


def test_build_messages_includes_disposition_brief():
    from app.services.generator import _build_messages_for_chat

    brief = {
        "authoritative_summary": "Graph rank #1 is Fracture.",
        "primary_condition": "Fracture",
        "primary_score": 8.5,
        "minimum_triage_level": "urgent_care",
        "insufficient_evidence": False,
        "ranked_conditions": [{"condition": "Fracture", "score": 8.5}],
        "matched_factors": ["Recent trauma"],
        "evidence_factors": [],
    }
    messages = _build_messages_for_chat(
        "What should I do?",
        [{"source": "paper", "snippet": "seek care"}],
        None,
        disposition_brief=brief,
    )
    assert messages[0]["role"] == "system"
    assert "<thinking>" not in messages[0]["content"]
    user_content = messages[-1]["content"]
    assert "Graph disposition brief (AUTHORITATIVE" in user_content
    assert "Primary condition: Fracture" in user_content
    assert "Evidence:" in user_content
    assert "<thinking>" not in user_content


def test_extract_answer_text_unclosed_answer_and_echo_guard():
    from app.services.generator import extract_answer_text, looks_like_instruction_echo

    leaked = (
        "`.\n2.  **Accuracy:** Strictly follow the `graph disposition brief`.\n"
        "</thinking>\n<answer>\nPlease go to the emergency department now."
    )
    assert extract_answer_text(leaked) == "Please go to the emergency department now."
    assert looks_like_instruction_echo(leaked) is False
    assert looks_like_instruction_echo(
        "2. **Accuracy:** Strictly follow the graph disposition brief."
    )


def test_extract_response_text_raises_on_empty_max_tokens():
    part = MagicMock()
    part.thought = False
    part.text = ""
    content = MagicMock()
    content.parts = [part]
    candidate = MagicMock()
    candidate.content = content
    candidate.finish_reason = 2  # MAX_TOKENS
    candidate.safety_ratings = None
    response = MagicMock()
    response.candidates = [candidate]
    response.text = ""
    with pytest.raises(GenerationEmptyError) as exc:
        _extract_response_text(response)
    assert "MAX_TOKENS" in str(exc.value) or "generation_empty" in str(exc.value)
