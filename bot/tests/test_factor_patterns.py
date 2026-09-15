"""Unit tests for factor pattern helpers."""

import pytest

from app.services.rag.factor_patterns import (
    _severity_implies_not_severe,
    _severity_implies_severe,
    _sex_factor,
    pain_score_0_to_10,
)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("female", "Female sex"),
        ("woman", "Female sex"),
        ("I am a woman", "Female sex"),
        ("male", "Male sex"),
        ("man", "Male sex"),
        ("I'm a man", "Male sex"),
        ("gentleman", "Male sex"),
        ("lady", "Female sex"),
    ],
)
def test_sex_factor_word_boundaries(text: str, expected: str):
    assert _sex_factor(text) == expected


def test_sex_factor_female_not_male_substring():
    assert _sex_factor("female") == "Female sex"
    assert _sex_factor("female") != "Male sex"


def test_sex_factor_woman_not_man_substring():
    assert _sex_factor("woman") == "Female sex"


def test_sex_factor_unknown_returns_none():
    assert _sex_factor("non-binary") is None


def test_pain_score_short_reply_and_scale():
    assert pain_score_0_to_10("6") == 6
    assert pain_score_0_to_10("its like a 6") == 6
    assert pain_score_0_to_10("8/10") == 8
    assert pain_score_0_to_10("7 out of 10") == 7
    assert pain_score_0_to_10("I'm 52") is None


def test_severity_helpers_numeric_and_words():
    assert _severity_implies_not_severe("its like a 6") is True
    assert _severity_implies_severe("its like a 6") is False
    assert _severity_implies_severe("8/10") is True
    assert _severity_implies_severe("severe pain") is True
    assert _severity_implies_not_severe("mild") is True
