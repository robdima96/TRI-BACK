"""Pain severity on 0–10 scale and descriptive severity extraction."""

from app.services.encoder import _pain_severity_band, build_clinical_checklist

_SEVERITY_LABEL = "symptom_severity"


def test_pain_severity_band_mapping():
    assert _pain_severity_band(0) == "mild"
    assert _pain_severity_band(3) == "mild"
    assert _pain_severity_band(4) == "moderate"
    assert _pain_severity_band(6) == "moderate"
    assert _pain_severity_band(7) == "severe"
    assert _pain_severity_band(10) == "severe"
    assert _pain_severity_band(11) is None


def _severity_items(msg: str):
    cl = build_clinical_checklist(msg)
    return [it for it in cl.items if it.kind == "severity"]


def test_seven_out_of_ten_symptom_severity():
    items = _severity_items("the pain is constant and 7 out of 10")
    assert len(items) == 1
    assert items[0].text == "7 out of 10"
    assert items[0].label == _SEVERITY_LABEL


def test_slash_ten_ratings_symptom_severity():
    for msg in ("pain 3/10", "pain 5/10", "pain 8/10"):
        assert _severity_items(msg)[0].label == _SEVERITY_LABEL


def test_descriptive_severe_pain_symptom_severity():
    items = _severity_items("severe pain")
    assert len(items) == 1
    assert items[0].text == "severe"
    assert items[0].label == _SEVERITY_LABEL


def test_descriptive_moderate_word():
    items = _severity_items("moderate low back pain")
    assert any(
        it.label == _SEVERITY_LABEL and it.text == "moderate" for it in items
    )


def test_mild_bruising_not_pain_severity():
    items = _severity_items(
        "i have some mild bruising and tenderness at the site of the fall"
    )
    assert not any(it.text == "mild" for it in items)
