from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_chat_endpoint_returns_response():
    response = client.post(
        "/api/v1/chat",
        json={"session_id": "s-001", "message": "I have low back pain for 2 weeks."},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["session_id"] == "s-001"
    assert payload["response"]
    assert isinstance(payload["citations"], list)
    assert payload["escalated"] is False


def test_chat_endpoint_escalates_on_red_flag():
    response = client.post(
        "/api/v1/chat",
        json={"session_id": "s-002", "message": "I have chest pain and cannot breathe."},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["escalated"] is True
    assert payload["safety_reason"] is not None


def test_chat_endpoint_rejects_blank_session_id():
    response = client.post(
        "/api/v1/chat",
        json={"session_id": "   ", "message": "hello"},
    )
    assert response.status_code == 400
