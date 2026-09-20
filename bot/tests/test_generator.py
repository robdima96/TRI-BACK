"""Generator backend selection and routing."""

from unittest.mock import MagicMock, patch

import pytest

from app.config import settings
from app.services.generator import (
    DISPOSITION_THINKING_LEVEL,
    GENERATOR_SYSTEM_FAILURE_TEXT,
    _generator_unavailable_stub,
    generate_from_messages,
    generate_response,
    generate_response_result,
    generator_model_configured,
    generator_status_detail,
)
from app.services.generator_backends import (
    DEFAULT_THINKING_LEVEL,
    GenerationEmptyError,
    _extract_response_text,
    _split_system_messages,
    _to_contents,
    generate_vertex,
    vertex_location_is_regional,
    vertex_location_problem,
)
from app.schemas import Evidence


@pytest.fixture
def vertex_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "generator_backend", "vertex")
    monkeypatch.setattr(settings, "generator_model", "gemini-3.5-flash-lite")
    monkeypatch.setattr(settings, "vertex_project_id", "test-project")
    monkeypatch.setattr(settings, "vertex_location", "us")
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
    assert "gemini-3.5-flash-lite" in generator_status_detail()


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
    assert mock_vertex.call_args.kwargs["thinking_level"] is None
    assert mock_vertex.call_args.kwargs["response_mime_type"] is None


@patch("app.services.generator_backends.generate_vertex")
def test_generate_from_messages_forwards_thinking_and_schema(
    mock_vertex, vertex_settings
):
    mock_vertex.return_value = '{"ok": true}'
    schema = {"type": "OBJECT"}
    generate_from_messages(
        [{"role": "user", "content": "hello"}],
        max_new_tokens=32,
        thinking_level="MEDIUM",
        response_mime_type="application/json",
        response_schema=schema,
    )
    kwargs = mock_vertex.call_args.kwargs
    assert kwargs["thinking_level"] == "MEDIUM"
    assert kwargs["response_mime_type"] == "application/json"
    assert kwargs["response_schema"] is schema


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
    candidate.finish_reason = "MAX_TOKENS"
    candidate.safety_ratings = None
    response = MagicMock()
    response.candidates = [candidate]
    response.text = ""
    with pytest.raises(GenerationEmptyError) as exc:
        _extract_response_text(response)
    assert "MAX_TOKENS" in str(exc.value)


def test_extract_response_text_skips_thought_parts():
    thought = MagicMock()
    thought.thought = True
    thought.text = "internal reasoning"
    answer = MagicMock()
    answer.thought = False
    answer.text = "Go to urgent care."
    content = MagicMock()
    content.parts = [thought, answer]
    candidate = MagicMock()
    candidate.content = content
    candidate.finish_reason = "STOP"
    candidate.safety_ratings = None
    response = MagicMock()
    response.candidates = [candidate]
    assert _extract_response_text(response) == "Go to urgent care."


def test_split_system_and_contents_mapping():
    class FakePart:
        @staticmethod
        def from_text(text=""):
            return text

    class FakeContent:
        def __init__(self, role, parts):
            self.role = role
            self.parts = parts

    types = MagicMock()
    types.Part = FakePart
    types.Content = FakeContent

    instruction, rest = _split_system_messages(
        [
            {"role": "system", "content": "Be brief."},
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
            {"role": "user", "content": "again"},
        ]
    )
    assert instruction == "Be brief."
    contents = _to_contents(rest, types)
    assert [c.role for c in contents] == ["user", "model", "user"]
    assert contents[-1].role == "user"


def test_to_contents_rejects_trailing_model_turn():
    class FakePart:
        @staticmethod
        def from_text(text=""):
            return text

    class FakeContent:
        def __init__(self, role, parts):
            self.role = role
            self.parts = parts

    types = MagicMock()
    types.Part = FakePart
    types.Content = FakeContent
    with pytest.raises(ValueError, match="last contents turn"):
        _to_contents(
            [
                {"role": "user", "content": "hi"},
                {"role": "assistant", "content": "hello"},
            ],
            types,
        )


def test_generate_vertex_thinking_config_and_no_temperature(vertex_settings, monkeypatch):
    captured: dict = {}

    class FakePart:
        @staticmethod
        def from_text(text=""):
            return text

    class FakeContent:
        def __init__(self, role, parts):
            self.role = role
            self.parts = parts

    class FakeThinkingConfig:
        def __init__(self, **kwargs):
            captured["thinking"] = kwargs

    class FakeGenConfig:
        def __init__(self, **kwargs):
            captured["config"] = kwargs

    class FakeTypes:
        Part = FakePart
        Content = FakeContent
        ThinkingConfig = FakeThinkingConfig
        GenerateContentConfig = FakeGenConfig

    class FakeModels:
        def generate_content(self, *, model, contents, config):
            captured["model"] = model
            captured["contents"] = contents
            answer = MagicMock(thought=False, text="ok")
            content = MagicMock(parts=[answer])
            candidate = MagicMock(
                content=content, finish_reason="STOP", safety_ratings=None
            )
            return MagicMock(candidates=[candidate], text="ok")

    class FakeClient:
        models = FakeModels()

    import app.services.generator_backends as gb

    monkeypatch.setattr(gb, "_vertex_client", FakeClient())
    monkeypatch.setattr(gb, "_genai_types", lambda: FakeTypes)

    out = generate_vertex(
        [{"role": "system", "content": "sys"}, {"role": "user", "content": "hi"}],
        max_new_tokens=64,
        temperature=0.05,
        thinking_level=None,
    )
    assert out == "ok"
    assert captured["model"] == "gemini-3.5-flash-lite"
    assert captured["thinking"]["thinking_level"] == DEFAULT_THINKING_LEVEL
    assert captured["thinking"]["include_thoughts"] is False
    assert "temperature" not in captured["config"]
    assert "top_p" not in captured["config"]
    assert captured["config"]["max_output_tokens"] == 64
    assert captured["config"]["system_instruction"] == "sys"


@patch("app.services.generator.generate_from_messages")
def test_generate_response_requests_minimal_thinking(mock_gen, vertex_settings):
    mock_gen.return_value = "Please go to urgent care."
    text = generate_response("back pain", [])
    assert text == "Please go to urgent care."
    assert mock_gen.call_args.kwargs["thinking_level"] == DISPOSITION_THINKING_LEVEL
    assert DISPOSITION_THINKING_LEVEL == "MINIMAL"


def test_vertex_location_rejects_cloud_run_regions():
    assert vertex_location_is_regional("us-central1") is True
    assert vertex_location_is_regional("europe-west1") is True
    assert vertex_location_is_regional("us") is False
    assert vertex_location_is_regional("global") is False
    assert vertex_location_problem("us-central1")
    assert vertex_location_problem("us") is None


def test_generator_not_configured_for_regional_vertex_location(
    vertex_settings, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(settings, "vertex_location", "us-central1")
    assert generator_model_configured() is False
    detail = generator_status_detail()
    assert "us-central1" in detail
    assert "multi-region" in detail


def test_ensure_vertex_client_refuses_regional_location(
    vertex_settings, monkeypatch: pytest.MonkeyPatch
):
    import app.services.generator_backends as gb

    monkeypatch.setattr(settings, "vertex_location", "us-central1")
    monkeypatch.setattr(gb, "_vertex_client", None)
    with pytest.raises(RuntimeError, match="us-central1"):
        gb._ensure_vertex_client()


def test_extract_response_text_raises_on_empty_unknown_finish():
    part = MagicMock()
    part.thought = False
    part.text = ""
    content = MagicMock()
    content.parts = [part]
    candidate = MagicMock()
    candidate.content = content
    candidate.finish_reason = None
    candidate.safety_ratings = None
    response = MagicMock()
    response.candidates = [candidate]
    response.prompt_feedback = None
    with pytest.raises(GenerationEmptyError) as exc:
        _extract_response_text(response)
    assert "finish_reason=unknown" in str(exc.value)


def test_extract_response_text_thought_only_does_not_leak():
    thought = MagicMock()
    thought.thought = True
    thought.text = "internal reasoning that must not leak"
    content = MagicMock()
    content.parts = [thought]
    candidate = MagicMock()
    candidate.content = content
    candidate.finish_reason = None
    candidate.safety_ratings = None
    response = MagicMock()
    response.candidates = [candidate]
    response.text = "internal reasoning that must not leak"
    response.prompt_feedback = None
    with pytest.raises(GenerationEmptyError) as exc:
        _extract_response_text(response)
    assert "internal reasoning" not in str(exc.value)


def _fake_vertex_stack(monkeypatch, generate_content):
    captured: dict = {"thinking_levels": []}

    class FakePart:
        @staticmethod
        def from_text(text=""):
            return text

    class FakeContent:
        def __init__(self, role, parts):
            self.role = role
            self.parts = parts

    class FakeThinkingConfig:
        def __init__(self, **kwargs):
            captured["thinking_levels"].append(kwargs.get("thinking_level"))
            self.thinking_level = kwargs.get("thinking_level")
            self.include_thoughts = kwargs.get("include_thoughts")

    class FakeGenConfig:
        def __init__(self, **kwargs):
            self.thinking_config = kwargs.get("thinking_config")
            captured["config"] = kwargs

    class FakeTypes:
        Part = FakePart
        Content = FakeContent
        ThinkingConfig = FakeThinkingConfig
        GenerateContentConfig = FakeGenConfig

    class FakeModels:
        def generate_content(self, *, model, contents, config):
            return generate_content(model=model, contents=contents, config=config)

    class FakeClient:
        models = FakeModels()

    import app.services.generator_backends as gb

    monkeypatch.setattr(gb, "_vertex_client", FakeClient())
    monkeypatch.setattr(gb, "_genai_types", lambda: FakeTypes)
    monkeypatch.setattr(gb, "_RETRY_SLEEP_SEC", 0)
    return captured


def _empty_candidate_response(*, finish=None, thought_only=False):
    part = MagicMock()
    part.thought = thought_only
    part.text = "secret" if thought_only else ""
    content = MagicMock(parts=[part])
    candidate = MagicMock(
        content=content, finish_reason=finish, safety_ratings=None
    )
    response = MagicMock()
    response.candidates = [candidate]
    response.text = ""
    response.prompt_feedback = None
    return response


def test_generate_vertex_retries_empty_medium_at_minimal(vertex_settings, monkeypatch):
    calls = {"n": 0}

    def generate_content(*, model, contents, config):
        calls["n"] += 1
        level = config.thinking_config.thinking_level
        if level == "MEDIUM":
            return _empty_candidate_response(finish=None, thought_only=True)
        answer = MagicMock(thought=False, text="Go to urgent care.")
        content = MagicMock(parts=[answer])
        candidate = MagicMock(
            content=content, finish_reason="STOP", safety_ratings=None
        )
        return MagicMock(candidates=[candidate], text="Go to urgent care.")

    captured = _fake_vertex_stack(monkeypatch, generate_content)
    out = generate_vertex(
        [{"role": "user", "content": "hi"}],
        max_new_tokens=64,
        thinking_level="MEDIUM",
    )
    assert out == "Go to urgent care."
    assert calls["n"] == 2
    assert captured["thinking_levels"] == ["MEDIUM", "MINIMAL"]


def test_generate_vertex_both_empty_raises(vertex_settings, monkeypatch):
    calls = {"n": 0}

    def generate_content(*, model, contents, config):
        calls["n"] += 1
        return _empty_candidate_response(finish=None)

    captured = _fake_vertex_stack(monkeypatch, generate_content)
    with pytest.raises(GenerationEmptyError, match="finish_reason=unknown"):
        generate_vertex(
            [{"role": "user", "content": "hi"}],
            max_new_tokens=64,
            thinking_level="MEDIUM",
        )
    assert calls["n"] == 2
    assert captured["thinking_levels"] == ["MEDIUM", "MINIMAL"]


def test_generate_vertex_minimal_empty_does_not_retry_identically(
    vertex_settings, monkeypatch
):
    calls = {"n": 0}

    def generate_content(*, model, contents, config):
        calls["n"] += 1
        return _empty_candidate_response(finish=None)

    captured = _fake_vertex_stack(monkeypatch, generate_content)
    with pytest.raises(GenerationEmptyError, match="finish_reason=unknown"):
        generate_vertex(
            [{"role": "user", "content": "hi"}],
            max_new_tokens=64,
            thinking_level="MINIMAL",
        )
    assert calls["n"] == 1
    assert captured["thinking_levels"] == ["MINIMAL"]


def test_generate_vertex_does_not_retry_404(vertex_settings, monkeypatch):
    class NotFound(Exception):
        status_code = 404

    def generate_content(*, model, contents, config):
        raise NotFound("Publisher model was not found")

    _fake_vertex_stack(monkeypatch, generate_content)
    with pytest.raises(NotFound):
        generate_vertex(
            [{"role": "user", "content": "hi"}],
            max_new_tokens=64,
            thinking_level="MINIMAL",
        )


@patch("app.services.generator.generate_from_messages")
def test_generate_response_result_kinds(mock_gen, vertex_settings):
    mock_gen.return_value = "Please go to urgent care."
    text, kind = generate_response_result("back pain", [])
    assert text == "Please go to urgent care."
    assert kind is None

    mock_gen.return_value = ""
    text, kind = generate_response_result("back pain", [])
    assert text == GENERATOR_SYSTEM_FAILURE_TEXT
    assert kind == "empty"

    mock_gen.return_value = (
        "Strictly follow the graph disposition brief. **Accuracy** is required."
    )
    text, kind = generate_response_result("back pain", [])
    assert text == GENERATOR_SYSTEM_FAILURE_TEXT
    assert kind == "echo"

    mock_gen.side_effect = GenerationEmptyError(
        "generation_empty: finish_reason=unknown"
    )
    text, kind = generate_response_result("back pain", [])
    assert text == GENERATOR_SYSTEM_FAILURE_TEXT
    assert kind == "empty"

    mock_gen.side_effect = RuntimeError("404 NOT_FOUND")
    text, kind = generate_response_result("back pain", [])
    assert text == GENERATOR_SYSTEM_FAILURE_TEXT
    assert kind == "error"


def test_generate_response_result_not_configured(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "generator_backend", "vertex")
    monkeypatch.setattr(settings, "vertex_project_id", None)
    text, kind = generate_response_result("back pain", [])
    assert text == GENERATOR_SYSTEM_FAILURE_TEXT
    assert kind == "not_configured"
