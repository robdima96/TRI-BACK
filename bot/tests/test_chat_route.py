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


def test_chat_refuses_when_graph_not_ready(monkeypatch):
    monkeypatch.setattr(
        "app.main.probe_graph",
        lambda: (False, "FactorSheetError: factors CSV missing"),
    )
    response = client.post(
        "/api/v1/chat",
        json={"session_id": "s-graph", "message": "I'm a 70 year old man"},
    )
    assert response.status_code == 503
    assert "FactorSheetError" in response.json()["detail"]


def test_chat_maps_pipeline_error_to_503(monkeypatch):
    from app.main import chat_graph

    monkeypatch.setattr("app.main.probe_graph", lambda: (True, "ok"))

    def boom(*_args, **_kwargs):
        raise RuntimeError("checkpoint locked")

    monkeypatch.setattr(chat_graph, "invoke", boom)
    response = client.post(
        "/api/v1/chat",
        json={"session_id": "s-boom", "message": "I'm a 70 year old man"},
    )
    assert response.status_code == 503
    assert response.json()["detail"] == "RuntimeError: checkpoint locked"


def test_chat_endpoint_rejects_blank_session_id():
    response = client.post(
        "/api/v1/chat",
        json={"session_id": "   ", "message": "hello"},
    )
    assert response.status_code == 400
