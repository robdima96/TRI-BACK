import hashlib
import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import settings
from app.main import app


def _session_file(session_id: str) -> Path:
    digest = hashlib.sha256(session_id.encode("utf-8")).hexdigest()
    return Path(settings.session_store_dir) / f"sess_{digest}.json"


client = TestClient(app)


def test_session_json_accumulates_transcript():
    sid = "sess-multi-1"
    r1 = client.post(
        "/api/v1/chat",
        json={"session_id": sid, "message": "First message about knee pain."},
    )
    assert r1.status_code == 200
    r2 = client.post(
        "/api/v1/chat",
        json={"session_id": sid, "message": "Follow-up: what about exercises?"},
    )
    assert r2.status_code == 200
    path = _session_file(sid)
    assert path.is_file()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert len(data["messages"]) >= 4
    assert data["messages"][0]["role"] == "user"
    assert data["messages"][1]["role"] == "assistant"
    assert "clinical_checklist" in data


def test_merge_checklist_dedupes():
    from app.orchestrator.checklist import merge_checklist_items
    from app.schemas import ChecklistItem

    prior = [
        {"text": "diabetes", "kind": "comorbidity", "source": "pattern", "label": "comorbidity"},
    ]
    current = [
        ChecklistItem(text="diabetes", kind="comorbidity", source="pattern", label="comorbidity"),
        ChecklistItem(text="2 weeks", kind="duration", source="pattern", label="duration"),
    ]
    merged = merge_checklist_items(prior, current)
    assert len(merged) == 2
