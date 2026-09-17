"""Conversational intake: fast-path polarity, graph-guarded question answers."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.orchestrator.nodes import (
    enrich_checklist_node,
    evaluate_coverage_node,
    generate_question_node,
    plan_question_node,
)
from app.schemas import ChecklistItem
from app.services.intake_enricher import IntakeEnrichmentResult
from app.services.question_brief import (
    CANNED_QUESTION_BRIEF,
    answer_patient_question,
    build_question_graph_packet,
)
from app.services.utterance_spans import UtteranceAnalysis


@pytest.fixture(autouse=True)
def _no_live_retrieval(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.config import settings

    monkeypatch.setattr(settings, "rag_load", False)
    monkeypatch.setattr(settings, "graphrag_load", False)


def _asked_state(message: str, **overrides):
    state = {
        "session_id": "sess-conv",
        "message": message,
        "message_normalized": message,
        "turn_start_checklist": [],
        "clinical_checklist": [],
        "encoder_turn_items": [],
        "extraction_history": [],
        "messages": [],
        "asked_factor": "Point tenderness",
        "last_asked_slot": None,
        "factor_states": {"Recent trauma": "affirmed"},
        "comorbidities_acknowledged": True,
        "coverage": {
            "session_complete": False,
            "symptoms_complete": False,
            "ready_for_disposition": False,
            "missing_slots": [{"slot": "age", "satisfied": False}],
            "active_symptom_id": None,
            "symptom_instances": [],
        },
        "risk_hits": [],
        "questions_asked": 3,
        "pending_intake_question": None,
        "pending_intake_slot": None,
    }
    state.update(overrides)
    return state


def test_press_on_it_is_question_only_and_reasks_point_tenderness():
    state = _asked_state(
        "should I press on it?",
        last_rank_topic="Fracture",
        last_rank_tier=1,
    )
    qa = (
        "You don't need to press on your back for this chat. I only need to know "
        "if you already notice a small spot on your spine that is distinctly sore."
    )
    with patch(
        "app.orchestrator.nodes.propose_checklist_enrichment",
    ) as enricher, patch(
        "app.orchestrator.nodes.answer_patient_question",
        return_value=qa,
    ) as mocked_qa:
        out = enrich_checklist_node(state)
        assert enricher.call_count == 0
        assert mocked_qa.call_count == 1
        assert mocked_qa.call_args.kwargs.get("asked_factor") == "Point tenderness"

    assert (out.get("factor_states") or {}).get("Point tenderness") != "affirmed"
    assert "Point tenderness" not in (out.get("factor_states") or {})
    from app.orchestrator.relevance_ranker import eligible_neighbour_factors

    assert "Point tenderness" in eligible_neighbour_factors(out.get("factor_states"))
    brief = out.get("patient_question_brief") or ""
    assert brief == qa
    assert not brief.startswith(CANNED_QUESTION_BRIEF)
    out["force_factor_ask"] = "Point tenderness"
    planned = plan_question_node(out)
    gen = generate_question_node(planned)
    text = gen["final_response"]
    assert text.startswith(brief)
    assert gen["asked_factor"] == "Point tenderness"
    assert "tender" in text.casefold() or "press" in text.casefold() or "spot" in text.casefold()


def test_mixed_severity_and_danger_question_captures_and_prefixes():
    enrichment = IntakeEnrichmentResult(
        status="applied",
        summary_reason="Recorded severe pain.",
        applied=[
            ChecklistItem(
                text="severe",
                kind="severity",
                source="llm",
                label="symptom_severity",
            )
        ],
        resulting_checklist=[
            {
                "text": "low back pain",
                "kind": "ner_entity",
                "source": "gliner",
                "label": "symptom",
            },
            {
                "text": "severe",
                "kind": "severity",
                "source": "llm",
                "label": "symptom_severity",
            },
        ],
        asked_factor_reply="not_answered",
        patient_answer=(
            "Severe pain is one of the screening topics on this graph; "
            "I am not giving a triage recommendation."
        ),
    )
    state = _asked_state(
        "my pain is severe. is my back pain dangerous?",
        asked_factor=None,
        last_asked_slot="symptom_quality",
        clinical_checklist=[
            {
                "text": "low back pain",
                "kind": "ner_entity",
                "source": "gliner",
                "label": "symptom",
            }
        ],
        factor_states={},
    )
    with patch(
        "app.orchestrator.nodes.propose_checklist_enrichment",
        return_value=enrichment,
    ) as mocked, patch(
        "app.orchestrator.nodes.answer_patient_question",
    ) as qa:
        out = enrich_checklist_node(state)
        assert mocked.call_count == 1
        assert qa.call_count == 0
        assert "dangerous" not in mocked.call_args.kwargs["latest_user_message"].casefold()
        assert mocked.call_args.kwargs.get("question_spans")
        assert mocked.call_args.kwargs.get("graph_packet")

    assert any(row.get("kind") == "severity" for row in out["clinical_checklist"])
    brief = out.get("patient_question_brief") or ""
    assert brief == enrichment.patient_answer
    assert not brief.startswith(CANNED_QUESTION_BRIEF)
    assert "see a surgeon" not in brief.casefold()

    covered = evaluate_coverage_node(out)
    planned = plan_question_node(covered)
    gen = generate_question_node(planned)
    text = gen["final_response"]
    assert text.startswith(brief)
    assert planned.get("slot_being_asked") != "symptom_severity"
    assert "how severe" not in text.casefold()


def test_unpunctuated_oa_mixed_runs_enricher_on_statement_span():
    analysis = UtteranceAnalysis(
        polarity_spans=["yes"],
        statement_spans=["I do have osteoarthritis"],
        question_spans=["what does that have to do with my back pain"],
        raw_spans=[
            "yes, I do have osteoarthritis",
            "what does that have to do with my back pain",
        ],
    )
    enrichment = IntakeEnrichmentResult(
        status="applied",
        summary_reason="Recorded osteoarthritis.",
        applied=[
            ChecklistItem(
                text="osteoarthritis",
                kind="comorbidity",
                source="llm",
                label="comorbidity",
            )
        ],
        resulting_checklist=[
            {
                "text": "osteoarthritis",
                "kind": "comorbidity",
                "source": "llm",
                "label": "comorbidity",
            }
        ],
        asked_factor_reply="affirmed",
        patient_answer=(
            "Osteoarthritis is one of the screening topics on this graph; "
            "it can relate to bone health when we ask about your back."
        ),
    )
    state = _asked_state(
        "yes, I do have osteoarthritis but what does that have to do with my back pain",
        asked_factor="Osteoarthritis",
        factor_states={},
    )
    with patch(
        "app.orchestrator.nodes.classify_utterance",
        return_value=analysis,
    ), patch(
        "app.orchestrator.nodes.propose_checklist_enrichment",
        return_value=enrichment,
    ) as mocked, patch(
        "app.orchestrator.nodes.answer_patient_question",
    ) as qa:
        out = enrich_checklist_node(state)
        assert mocked.call_count == 1
        assert qa.call_count == 0
        passed = mocked.call_args.kwargs["latest_user_message"]
        assert "osteoarthritis" in passed.casefold()
        assert "what does that" not in passed.casefold()

    assert out["factor_states"].get("Osteoarthritis") == "affirmed"
    assert any("osteoarthritis" in (row.get("text") or "").casefold() for row in out["clinical_checklist"])
    assert out.get("patient_question_brief") == enrichment.patient_answer


def test_bare_polarity_skips_enricher():
    for token in ("no", "yes", "idk"):
        state = _asked_state(token, asked_factor="Saddle anaesthesia", factor_states={})
        with patch("app.orchestrator.nodes.propose_checklist_enrichment") as mocked, patch(
            "app.orchestrator.nodes.answer_patient_question",
        ) as qa, patch(
            "app.services.question_brief.generate_from_messages",
        ) as gen, patch(
            "app.services.intake_enricher.generate_from_messages",
        ) as enrich_gen:
            out = enrich_checklist_node(state)
            assert mocked.call_count == 0, token
            assert qa.call_count == 0, token
            assert gen.call_count == 0, token
            assert enrich_gen.call_count == 0, token
        polarity = (out.get("factor_states") or {}).get("Saddle anaesthesia")
        if token == "idk":
            assert polarity == "unknown"
        elif token == "yes":
            assert polarity == "affirmed"
        else:
            assert polarity == "denied"


def test_if_i_stay_still_is_a_statement_and_runs_enricher():
    state = _asked_state(
        "if I stay still",
        asked_factor=None,
        last_asked_slot="palliative",
        factor_states={},
    )
    enrichment = IntakeEnrichmentResult(status="no_changes", summary_reason="kept")
    with patch(
        "app.orchestrator.nodes.propose_checklist_enrichment",
        return_value=enrichment,
    ) as mocked:
        enrich_checklist_node(state)
        assert mocked.call_count == 1


def test_steroids_statement_uses_enricher_polarity_not_six_word_rule():
    analysis = UtteranceAnalysis(
        statement_spans=["I take prednisone daily"],
        raw_spans=["I take prednisone daily"],
    )
    enrichment = IntakeEnrichmentResult(
        status="no_changes",
        summary_reason="steroids acknowledged",
        asked_factor_reply="affirmed",
    )
    state = _asked_state(
        "I take prednisone daily",
        asked_factor="Corticosteroids",
        factor_states={},
    )
    with patch(
        "app.orchestrator.nodes.classify_utterance",
        return_value=analysis,
    ), patch(
        "app.orchestrator.nodes.propose_checklist_enrichment",
        return_value=enrichment,
    ) as mocked:
        out = enrich_checklist_node(state)
        assert mocked.call_count == 1
    assert out["factor_states"]["Corticosteroids"] == "affirmed"


def test_enricher_not_answered_does_not_get_heuristic_overwrite():
    analysis = UtteranceAnalysis(
        statement_spans=["I take prednisone daily"],
        raw_spans=["I take prednisone daily"],
    )
    enrichment = IntakeEnrichmentResult(
        status="no_changes",
        summary_reason="did not answer the asked factor",
        asked_factor_reply="not_answered",
    )
    state = _asked_state(
        "I take prednisone daily",
        asked_factor="Point tenderness",
        factor_states={},
    )
    with patch(
        "app.orchestrator.nodes.classify_utterance",
        return_value=analysis,
    ), patch(
        "app.orchestrator.nodes.propose_checklist_enrichment",
        return_value=enrichment,
    ):
        out = enrich_checklist_node(state)
    assert "Point tenderness" not in (out.get("factor_states") or {})


def test_yes_plus_question_credits_and_prefixes():
    state = _asked_state(
        "yes. is that bad?",
        asked_factor="Point tenderness",
        factor_states={},
    )
    with patch("app.orchestrator.nodes.propose_checklist_enrichment") as mocked, patch(
        "app.orchestrator.nodes.answer_patient_question",
        return_value="That factor is a small spot on the spine that is sore to press.",
    ) as qa:
        out = enrich_checklist_node(state)
        assert mocked.call_count == 0
        assert qa.call_count == 1
    assert out["factor_states"]["Point tenderness"] == "affirmed"
    assert out.get("patient_question_brief")
    assert not (out.get("patient_question_brief") or "").startswith(CANNED_QUESTION_BRIEF)


def test_like_what_after_comorbidities_calls_qa_not_enricher():
    qa = (
        "Things like diabetes, steroid tablets, or previous cancer — "
        "those are the health conditions this screen asks about."
    )
    from app.config import settings

    state = _asked_state(
        "like what?",
        asked_factor=None,
        last_asked_slot="comorbidities",
        comorbidities_acknowledged=False,
        factor_states={},
        questions_asked=max(0, settings.max_questions - 1),
        coverage={
            "session_complete": False,
            "symptoms_complete": False,
            "ready_for_disposition": False,
            "missing_slots": [{"slot": "comorbidities", "satisfied": False}],
            "active_symptom_id": None,
            "symptom_instances": [],
        },
    )
    with patch(
        "app.orchestrator.nodes.propose_checklist_enrichment",
    ) as enricher, patch(
        "app.orchestrator.nodes.answer_patient_question",
        return_value=qa,
    ) as mocked_qa:
        out = enrich_checklist_node(state)
        assert enricher.call_count == 0
        assert mocked_qa.call_count == 1
        assert mocked_qa.call_args.kwargs.get("last_asked_slot") == "comorbidities"

    brief = out.get("patient_question_brief") or ""
    assert brief == qa
    assert not brief.startswith(CANNED_QUESTION_BRIEF)
    assert "diabetes" in brief.casefold()
    planned = plan_question_node(out)
    gen = generate_question_node(planned)
    assert planned.get("slot_being_asked") == "comorbidities"
    assert gen["final_response"].startswith(qa)


def test_question_packet_includes_point_tenderness_and_comorbidities_slot():
    factor_packet = build_question_graph_packet(
        ["should I press on it?"],
        asked_factor="Point tenderness",
    )
    assert "Point tenderness" in factor_packet
    assert "spot" in factor_packet.casefold() or "press" in factor_packet.casefold()

    slot_packet = build_question_graph_packet(
        ["like what?"],
        last_asked_slot="comorbidities",
    )
    assert "comorbidities" in slot_packet.casefold()
    assert "Diabetes" in slot_packet or "diabetes" in slot_packet.casefold()


@patch("app.services.question_brief.generate_from_messages")
@patch("app.services.question_brief.generator_model_configured", return_value=True)
def test_answer_patient_question_parses_json(mock_cfg, mock_gen):
    mock_gen.return_value = '{"answer": "Diabetes, steroid tablets, or previous cancer."}'
    answer = answer_patient_question(
        ["like what?"],
        last_asked_slot="comorbidities",
    )
    assert "diabetes" in answer.casefold()
    assert not answer.startswith(CANNED_QUESTION_BRIEF)
    prompt = mock_gen.call_args[0][0][0]["content"]
    assert "like what?" in prompt.casefold()
    assert "Diabetes" in prompt or "diabetes" in prompt.casefold()


@patch("app.services.question_brief.generator_model_configured", return_value=False)
def test_question_brief_canned_when_generator_down(mock_cfg):
    brief = answer_patient_question(["what colour is the sky?"], asked_factor=None)
    assert brief == CANNED_QUESTION_BRIEF
