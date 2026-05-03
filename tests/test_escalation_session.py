"""Escalation uses current-turn checklist only (session transcript can mention prior red flags)."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_escalation_drops_when_follow_up_has_no_red_flags():
    sid = "sess-escalation-followup"
    r1 = client.post(
        "/api/v1/chat",
        json={
            "session_id": sid,
            "message": "I have chest pain and cannot breathe.",
        },
    )
    assert r1.status_code == 200
    assert r1.json()["escalated"] is True

    r2 = client.post(
        "/api/v1/chat",
        json={
            "session_id": sid,
            "message": "Actually I feel fine now, just asking about stretching exercises.",
        },
    )
    assert r2.status_code == 200
    assert r2.json()["escalated"] is False
