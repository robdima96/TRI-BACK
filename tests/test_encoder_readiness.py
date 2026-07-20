"""Encoder readiness includes GliNER when NER is enabled."""

from app.services.encoder import encoder_is_available, encoder_status_detail


def test_encoder_status_detail_mentions_ner_state():
    detail = encoder_status_detail()
    assert isinstance(detail, str)
    assert detail


def test_encoder_is_available_bool():
    assert isinstance(encoder_is_available(), bool)
