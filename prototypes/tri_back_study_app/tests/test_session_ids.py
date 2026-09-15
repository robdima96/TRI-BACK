"""Session ID allocation tests."""

from tri_back_study_app.auth.session_ids import allocate_session_id


def test_participant_session_ids():
    assert allocate_session_id("425", "participant", 1) == "425_1"
    assert allocate_session_id("425", "participant", 2) == "425_2"


def test_admin_session_ids():
    assert allocate_session_id("admin", "admin", 1) == "admin_1"
    assert allocate_session_id("admin", "admin", 3) == "admin_3"
