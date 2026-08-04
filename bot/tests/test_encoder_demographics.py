"""Demographic pattern extraction (age, sex) on clinical checklist."""

from app.services.encoder import build_clinical_checklist


def _labels(items, label: str) -> list[str]:
    return [it.text for it in items if it.label == label]


def test_age_from_year_old_female_vignette():
    msg = (
        "i am a 27 year old female. i have pain in the lower back after a bad fall."
    )
    cl = build_clinical_checklist(msg)
    ages = _labels(cl.items, "age")
    sexes = _labels(cl.items, "sex")
    assert "27" in ages
    assert "female" in sexes
    assert not any(it.text == "27 year" and it.label == "duration" for it in cl.items)


def test_age_patient_age_and_dob():
    msg = "patient age is 65. date of birth 03/15/1980."
    cl = build_clinical_checklist(msg)
    ages = _labels(cl.items, "age")
    assert "65" in ages
    assert "03/15/1980" in ages


def test_sex_from_gender_field():
    msg = "biological sex: female. low back pain."
    cl = build_clinical_checklist(msg)
    assert "female" in _labels(cl.items, "sex")


def test_sex_with_words_between_year_old_and_male():
    msg = (
        "i am a 20 year old avid male sportsman with low back pain and stiffness."
    )
    cl = build_clinical_checklist(msg)
    assert "20" in _labels(cl.items, "age")
    assert "male" in _labels(cl.items, "sex")


def test_sex_from_guy_and_dude():
    assert "male" in _labels(
        build_clinical_checklist("i am a guy with low back pain.").items, "sex"
    )
    assert "male" in _labels(
        build_clinical_checklist("i'm a 30 year old dude, pain in my knee.").items,
        "sex",
    )


def test_age_from_bare_i_am_number():
    msg = "I am 70 with fever and night pain."
    cl = build_clinical_checklist(msg)
    assert "70" in _labels(cl.items, "age")


def test_no_age_without_trigger():
    msg = "chronic low back pain for many months."
    cl = build_clinical_checklist(msg)
    assert _labels(cl.items, "age") == []
