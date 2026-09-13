"""Unit tests for MedQA LBP screening filters (no Hugging Face download)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib.counts import new_audit
from lib.lexicon import (
    is_cervical_only,
    is_isolated_radiology,
    is_lumbar_puncture_only,
    is_vignette,
    lexicon_hit,
    preview_red_flag_family,
)
from lib.load_medqa import load_medqa_jsonl
from lib.patient import EchoBackend, PatientAgent, flag_reply
from lib.screen import screen_items, stratified_sample
from lib.cards import from_agentclinic_osce, patient_actor_only


def test_lexicon_keeps_sciatica_vignette():
    text = (
        "A 26-year-old woman presents with sudden-onset lower back pain radiating "
        "down the leg after exercising at the gym."
    )
    hit = lexicon_hit(text)
    assert hit.matched
    assert "low_back" in hit.terms or "sciatica" in hit.terms or "back_pain" in hit.terms
    ok, reason = is_vignette(text)
    assert ok, reason


def test_lumbar_puncture_only_dropped():
    text = "Which of the following is a contraindication to lumbar puncture?"
    hit = lexicon_hit(text)
    assert hit.matched  # 'lumbar' hits
    assert is_lumbar_puncture_only(text, hit.terms)


def test_cervical_only():
    text = "A 40-year-old man presents with neck pain after a rear-end collision."
    assert is_cervical_only(text)
    text2 = "A 40-year-old man presents with low back pain and neck stiffness."
    assert not is_cervical_only(text2)


def test_screen_fixture_counts():
    path = ROOT / "tests" / "fixtures" / "tiny_medqa.jsonl"
    items = load_medqa_jsonl(path, split="test")
    audit = new_audit(corpus="medqa_us", source_detail=str(path), seed=1)
    rows, survivors = screen_items(items, audit)
    names = [s.name for s in audit.stages]
    assert names == ["raw", "lexical", "vignette_heuristic", "auto_cervical_only"]
    assert audit.stages[0].n_out == len(items)
    # Fixture has 1 sciatica vignette, 1 LP factoid, 1 cervical, 1 anatomy factoid.
    ids = {i.source_id for i in survivors}
    assert "keep_sciatica" in ids
    assert "drop_lp" not in ids
    assert "drop_cervical" not in ids
    assert "drop_anatomy" not in ids
    sampled = stratified_sample(survivors, audit, n=20, seed=1)
    audit.finalize_grid()
    assert len(sampled) >= 1
    keep_row = next(r for r in rows if r.source_id == "keep_sciatica")
    assert keep_row.auto_red_flag_family == "mechanical"
    empty_status = {fam: cell.status for fam, cell in audit.grid.items() if cell.sampled_n == 0}
    assert all(s == "unknown" for s in empty_status.values())
    assert any(r.drop_reason == "lumbar_puncture_only" for r in rows)


def test_patient_agent_echo_does_not_see_hidden():
    osce = json.loads(
        (ROOT / "tests" / "fixtures" / "tiny_agentclinic.jsonl").read_text(encoding="utf-8").splitlines()[0]
    )
    card = from_agentclinic_osce(osce, source_id="x", stem_hash="abcd1234ffffeeee")
    actor = patient_actor_only(card)
    assert "Hidden" not in actor
    hidden = card["Hidden"]
    assert set(hidden) <= {"reference_disposition", "reference_labels", "must_elicit"}
    assert "objective_for_bot" not in hidden
    assert "physical_exam_if_any" not in hidden
    assert "test_results_if_any" not in hidden
    assert "correct_diagnosis" not in hidden
    assert card["Hidden"]["reference_labels"] == []
    agent = PatientAgent(card, EchoBackend(actor))
    opening = agent.opening()
    assert opening
    reply = agent.reply("How long has this been going on?")
    assert "not sure" in reply.lower() or "nobody" in reply.lower()
    assert not flag_reply(opening)
    assert actor["persona"] == {
        "personality": "neutral",
        "language_proficiency": "advanced",
        "medical_history_recall": "high_recall",
        "cognitive_confusion": "normal",
    }


def test_persona_closed_set_and_defaults():
    from lib.cards import DEFAULT_PERSONA, resolve_persona

    assert resolve_persona(None) == DEFAULT_PERSONA
    custom = resolve_persona(
        {
            "personality": "verbose",
            "language_proficiency": "basic",
            "medical_history_recall": "low_recall",
            "cognitive_confusion": "highly_confused",
        }
    )
    assert custom["personality"] == "verbose"
    assert custom["cognitive_confusion"] == "highly_confused"
    try:
        resolve_persona({"verbosity": "terse"})
        raise AssertionError("expected ValueError for old persona keys")
    except ValueError:
        pass
    try:
        resolve_persona({"personality": "terse"})
        raise AssertionError("expected ValueError for unknown personality")
    except ValueError:
        pass


def test_reference_labels_closed_set():
    from lib.cards import REFERENCE_LABEL_VALUES, resolve_reference_labels

    assert resolve_reference_labels(None) == []
    assert resolve_reference_labels([]) == []
    assert resolve_reference_labels(["CES", "vascular"]) == ["CES", "vascular"]
    assert list(REFERENCE_LABEL_VALUES) == [
        "mechanical",
        "CES",
        "fracture",
        "malignancy",
        "infection",
        "vascular",
    ]
    try:
        resolve_reference_labels(["inflammatory"])
        raise AssertionError("expected ValueError for inflammatory")
    except ValueError:
        pass
    try:
        resolve_reference_labels(["mechanical low back pain"])
        raise AssertionError("expected ValueError for free-text label")
    except ValueError:
        pass


def test_preview_family_ces():
    assert preview_red_flag_family("saddle anesthesia and cauda equina") == "ces"


def test_preview_family_ignores_denied_weight_loss():
    text = (
        "A 26-year-old woman presents with sudden-onset lower back pain radiating "
        "down the side of her leg. She denies fever, weight loss, and changes in "
        "bowel or bladder function."
    )
    assert preview_red_flag_family(text) == "mechanical"


def test_isolated_radiology():
    text = "Identify the radiographic sign shown below of the lumbar spine."
    assert is_isolated_radiology(text)


def test_osteomyelitis_not_spine_is_not_lexicon():
    hit = lexicon_hit("Osteomyelitis of the femur is most often caused by Staphylococcus.")
    assert "discitis" not in hit.terms


def test_confounder_dvt_and_abscess():
    dvt = lexicon_hit(
        "A 48-year-old woman presents with low back pain. Duplex ultrasound shows a pelvic DVT."
    )
    assert "confounder_dvt" in dvt.terms
    abscess = lexicon_hit(
        "A 32-year-old man with IV drug use presents with fever and a spinal epidural abscess."
    )
    assert "confounder_abscess" in abscess.terms or "epidural_abscess" in abscess.terms
    viscera = lexicon_hit("Acute pancreatitis with pain radiating to the back after alcohol binge.")
    assert "confounder_pancreas" not in viscera.terms
    assert "confounder_radiating_abdomen" not in viscera.terms
    assert not viscera.matched


def test_stage_arithmetic():
    path = ROOT / "tests" / "fixtures" / "tiny_medqa.jsonl"
    items = load_medqa_jsonl(path, split="test")
    audit = new_audit(corpus="medqa_us", source_detail=str(path), seed=1)
    screen_items(items, audit)
    for stage in audit.stages:
        assert stage.dropped == stage.n_in - stage.n_out
        assert sum(stage.drop_reasons.values()) == stage.dropped


def test_vertex_cli_model_wins():
    import os

    from lib.vertex_config import resolve_vertex_model

    name, source = resolve_vertex_model("gemini-2.0-flash")
    assert name == "gemini-2.0-flash"
    assert source == "cli --model"
    prev = os.environ.get("PATIENT_VERTEX_MODEL")
    os.environ["PATIENT_VERTEX_MODEL"] = "gemini-overlay-test"
    try:
        name, source = resolve_vertex_model(None)
        assert name == "gemini-overlay-test"
        assert source == "PATIENT_VERTEX_MODEL"
    finally:
        if prev is None:
            os.environ.pop("PATIENT_VERTEX_MODEL", None)
        else:
            os.environ["PATIENT_VERTEX_MODEL"] = prev


def test_make_backend_vertex_alias():
    from lib.patient import VertexBackend, make_backend

    # Construction reads project from bot/.env; skip if unset.
    try:
        backend = make_backend("gemini", {}, model="gemini-2.5-flash")
    except RuntimeError as exc:
        if "DIGIMSK_VERTEX_PROJECT_ID" in str(exc):
            return
        raise
    assert isinstance(backend, VertexBackend)
    assert backend.model == "gemini-2.5-flash"


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in tests:
        fn()
        print(f"ok {fn.__name__}")
    print(f"{len(tests)} tests passed")

