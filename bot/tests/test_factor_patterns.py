"""Unit tests for factor pattern helpers."""

import pytest

from app.services.rag.factor_patterns import _sex_factor


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
