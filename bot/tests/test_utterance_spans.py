"""Local SaT + miniBERT speech-act routing (mocked in CI)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from app.services.utterance_spans import (
    classify_span_kind,
    classify_utterance,
    query_classifier_configured,
    reset_utterance_models,
    sat_splitter_configured,
    split_idea_spans,
)


def test_fallback_labels_question_and_statement():
    assert classify_span_kind("should I press on it?") == "question"
    assert classify_span_kind("if I stay still") == "statement"


def test_whole_message_polarity_is_not_a_statement():
    analysis = classify_utterance("no")
    assert analysis.polarity_only
    assert not analysis.has_statement
    assert not analysis.has_question

    yes = classify_utterance("yes")
    assert yes.polarity_only

    idk = classify_utterance("idk")
    assert idk.polarity_only


def test_punctuated_mixed_statement_and_question():
    analysis = classify_utterance("my pain is severe. is my back pain dangerous?")
    assert analysis.has_statement
    assert analysis.has_question
    assert any("severe" in s.casefold() for s in analysis.statement_spans)
    assert any("dangerous" in s.casefold() for s in analysis.question_spans)


def test_leading_yes_is_not_polarity_only_for_the_whole_message():
    with patch(
        "app.services.utterance_spans.split_idea_spans",
        return_value=[
            "yes, I do have osteoarthritis",
            "what does that have to do with my back pain",
        ],
    ), patch(
        "app.services.utterance_spans.classify_span_kind",
        side_effect=lambda text: (
            "question" if "what does that" in text.casefold() else "statement"
        ),
    ):
        analysis = classify_utterance(
            "yes, I do have osteoarthritis but what does that have to do with my back pain"
        )
    assert analysis.has_polarity
    assert analysis.has_statement
    assert analysis.has_question
    assert not analysis.polarity_only


def test_denial_statement_is_not_peeled_to_bare_no():
    analysis = classify_utterance("no bladder problems")
    assert analysis.has_statement
    assert not analysis.polarity_only
    assert "bladder" in " ".join(analysis.statement_spans).casefold()
    analysis = classify_utterance("should I press on it?")
    assert analysis.question_only
    assert not analysis.has_polarity


@pytest.mark.skipif(
    not (Path(r"E:\TRI-BACK\miniBERT_query_classifier") / "config.json").is_file(),
    reason="local miniBERT weights missing",
)
def test_local_minibert_labels(monkeypatch):
    from app.config import settings

    reset_utterance_models()
    monkeypatch.setattr(
        settings, "query_classifier_dir", r"E:\TRI-BACK\miniBERT_query_classifier"
    )
    monkeypatch.setattr(settings, "query_classifier_load", True)
    assert query_classifier_configured()
    assert classify_span_kind("should I press on it?") == "question"
    assert classify_span_kind("if I stay still") == "statement"
    reset_utterance_models()


@pytest.mark.skipif(
    not (Path(r"E:\TRI-BACK\sat-3l-sm") / "config.json").is_file(),
    reason="local SaT weights missing",
)
def test_local_sat_splits_unpunctuated_mixed(monkeypatch):
    from app.config import settings

    reset_utterance_models()
    monkeypatch.setattr(settings, "sat_splitter_dir", r"E:\TRI-BACK\sat-3l-sm")
    monkeypatch.setattr(settings, "sat_splitter_load", True)
    assert sat_splitter_configured()
    from app.services.utterance_spans import _get_sat

    if _get_sat() is None:
        pytest.skip("wtpsplit/SaT failed to load")
    spans = split_idea_spans(
        "yes I do have osteoarthritis but what does that have to do with my back pain"
    )
    assert len(spans) >= 2
    reset_utterance_models()
