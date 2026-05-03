from app.services.preprocess import normalize_user_text


def test_normalize_applies_nfkc_and_case_folding():
    s = "CAF\u00E9"  # precomposed
    out = normalize_user_text(s)
    assert out == "café".casefold()


def test_normalize_collapse_whitespace():
    out = normalize_user_text("  hello \n  world  \r\t  ")
    assert out == "hello world"


def test_normalize_strips_zero_width():
    t = "chest\u200bpain"  # zero-width space
    out = normalize_user_text(t)
    assert out == "chestpain"


def test_empty_and_whitespace_only():
    assert normalize_user_text("") == ""
    assert normalize_user_text("   \n\t  ") == ""
