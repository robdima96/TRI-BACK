from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_ready_response_shape():
    r = client.get("/ready")
    assert r.status_code in (200, 503)
    data = r.json()
    assert data.get("status") in ("ready", "not_ready")
    checks = data.get("checks", {})
    for name in ("rag", "checkpointer", "generator", "encoder"):
        assert name in checks
        assert "ok" in checks[name] and isinstance(checks[name]["ok"], bool)
        assert "detail" in checks[name]
