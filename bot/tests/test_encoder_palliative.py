"""Encoder palliative / provocative cue extraction."""

from app.services.encoder import build_clinical_checklist


def _palliative_texts(msg: str) -> list[str]:
    return [it.text.casefold() for it in build_clinical_checklist(msg).items if it.kind == "palliative"]


def test_improved_by_exercise_is_palliative():
    texts = _palliative_texts(
        "My pain is improved by exercise, and it is worse when I sit for long periods."
    )
    assert any("improved" in t for t in texts)


def test_helps_to_improve_is_palliative():
    texts = _palliative_texts("Exercise helps to improve my pain. I already mentioned that")
    assert any("help" in t for t in texts)


def test_better_with_still_works():
    texts = _palliative_texts("Pain is better with ice and heat")
    assert any("better with" in t for t in texts)
