import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.session_store import session_file_path


def _session_file(session_id: str) -> Path:
    return session_file_path(session_id, root=Path(settings.session_store_dir))


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
    assert "extraction_history" in data
    assert len(data["extraction_history"]) >= 2
    assert "by_source" in data["extraction_history"][-1]
    assert "clinical_checklist" not in data["extraction_history"][-1]
    assert "engagement" in data
    assert "orchestrator" in data
    assert "orchestrator_history" in data
    assert len(data["orchestrator_history"]) >= 2
    assert "risk_hits" in data["orchestrator"]
    assert "escalated" in data["orchestrator"]
    assert "safety_reason" in data["orchestrator"]
    assert "disposition_history" in data


def test_study_session_id_uses_literal_filename():
    sid = "admin_15"
    r = client.post(
        "/api/v1/chat",
        json={"session_id": sid, "message": "I have back pain."},
    )
    assert r.status_code == 200
    path = _session_file(sid)
    assert path.name == "admin_15.json"
    assert path.is_file()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["session_id"] == sid
    assert data["orchestrator"]["escalated"] in (True, False)


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
    assert all(row.get("id") for row in merged)
    assert merged[0]["confirmed"] is False


def test_merge_checklist_preserves_stable_ids():
    from app.orchestrator.checklist import merge_checklist_items
    from app.schemas import ChecklistItem

    prior = [
        {
            "id": "cl_keep",
            "text": "diabetes",
            "kind": "comorbidity",
            "source": "pattern",
            "label": "comorbidity",
            "confirmed": True,
        },
    ]
    current = [
        ChecklistItem(text="diabetes", kind="comorbidity", source="pattern", label="comorbidity"),
        ChecklistItem(text="2 weeks", kind="duration", source="pattern", label="duration"),
    ]
    merged = merge_checklist_items(prior, current)
    assert merged[0]["id"] == "cl_keep"
    assert merged[0]["confirmed"] is True
    assert merged[1]["id"]
    assert merged[1]["text"] == "2 weeks"
