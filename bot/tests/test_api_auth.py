"""Tests for optional DIGIMSK_BOT_API_KEY on /api/v1/chat."""

from fastapi.testclient import TestClient

from app.config import settings
from app.main import app

client = TestClient(app)


def test_chat_allows_when_api_key_unset(monkeypatch):
    monkeypatch.setattr(settings, "bot_api_key", None)
    response = client.post(
        "/api/v1/chat",
        json={"session_id": "auth-open", "message": "I have low back pain for 2 weeks."},
    )
    assert response.status_code == 200


def test_chat_rejects_missing_bearer_when_key_set(monkeypatch):
    monkeypatch.setattr(settings, "bot_api_key", "test-secret-key")
    response = client.post(
        "/api/v1/chat",
        json={"session_id": "auth-deny", "message": "hello"},
    )
    assert response.status_code == 401


def test_chat_accepts_valid_bearer(monkeypatch):
    monkeypatch.setattr(settings, "bot_api_key", "test-secret-key")
    response = client.post(
        "/api/v1/chat",
        json={"session_id": "auth-ok", "message": "I have low back pain for 2 weeks."},
        headers={"Authorization": "Bearer test-secret-key"},
    )
    assert response.status_code == 200


def test_chat_rejects_wrong_bearer(monkeypatch):
    monkeypatch.setattr(settings, "bot_api_key", "test-secret-key")
    response = client.post(
        "/api/v1/chat",
        json={"session_id": "auth-bad", "message": "hello"},
        headers={"Authorization": "Bearer wrong"},
    )
    assert response.status_code == 401
