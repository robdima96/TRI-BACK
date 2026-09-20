"""One-shot rephrase endpoint helpers (no questions_asked increment)."""

from __future__ import annotations

from unittest.mock import patch

from app.services.rephrase import rephrase_session_message
from app.session_store import load_session, save_session


def _seed_question_session(tmp_path, monkeypatch, *, rephrased=False, question_mode=True):
    monkeypatch.setattr("app.config.settings.session_store_dir", tmp_path)
    monkeypatch.setattr("app.session_store.settings.session_store_dir", tmp_path)
    sid = "admin_99"
    save_session(
        sid,
        messages=[
            {"role": "user", "content": "hi", "message_id": "msg_000_u"},
            {
                "role": "assistant",
                "content": "How old are you?",
                "message_id": "msg_000",
                "question_mode": question_mode,
                "rephrased": rephrased,
            },
        ],
        orchestrator={"question_mode": question_mode, "questions_asked": 3},
        clinical_checklist=[{"text": "low back pain", "kind": "ner_entity", "label": "symptom"}],
        session_phase="intake",
    )
    return sid


def test_rephrase_rewrites_without_bumping_questions_asked(tmp_path, monkeypatch):
    sid = _seed_question_session(tmp_path, monkeypatch)
    with patch(
        "app.services.rephrase.rephrase_assistant_text",
        return_value="Could you tell me your age in years?",
    ):
        out = rephrase_session_message(session_id=sid, message_id="msg_000")
    assert out.ok
    assert out.questions_asked == 3
    stored = load_session(sid)
    assert stored["messages"][1]["content"] == "Could you tell me your age in years?"
    assert stored["messages"][1]["rephrased"] is True
    assert stored["orchestrator"]["questions_asked"] == 3


def test_rephrase_second_call_rejected(tmp_path, monkeypatch):
    sid = _seed_question_session(tmp_path, monkeypatch, rephrased=True)
    with patch("app.services.rephrase.rephrase_assistant_text") as mocked:
        out = rephrase_session_message(session_id=sid, message_id="msg_000")
        assert mocked.call_count == 0
    assert out.status == "already"
    assert out.questions_asked == 3


def test_rephrase_skips_non_question_bubbles(tmp_path, monkeypatch):
    sid = _seed_question_session(tmp_path, monkeypatch, question_mode=False)
    out = rephrase_session_message(session_id=sid, message_id="msg_000")
    assert out.status == "not_question"


def test_merge_keeps_rephrased_content(tmp_path, monkeypatch):
    sid = _seed_question_session(tmp_path, monkeypatch)
    with patch(
        "app.services.rephrase.rephrase_assistant_text",
        return_value="What is your age?",
    ):
        rephrase_session_message(session_id=sid, message_id="msg_000")
    save_session(
        sid,
        messages=[
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "How old are you?"},
        ],
    )
    stored = load_session(sid)
    assert stored["messages"][1]["content"] == "What is your age?"
    assert stored["messages"][1]["rephrased"] is True
    assert stored["messages"][1]["message_id"] == "msg_000"
