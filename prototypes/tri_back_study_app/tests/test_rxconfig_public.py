"""Public Reflex config uses the page origin, not a baked Cloud Run hostname."""

from rxconfig import public_reflex_settings


def test_local_pins_ports_and_does_not_set_api_url():
    settings = public_reflex_settings(public=False)
    assert settings["frontend_port"] == 3000
    assert settings["backend_port"] == 8000
    assert "api_url" not in settings
    assert "deploy_url" not in settings


def test_public_is_same_origin():
    settings = public_reflex_settings(public=True)
    assert settings["api_url"] == ""
    assert settings["deploy_url"] == ""
    assert settings["backend_port"] == 8000
    assert "frontend_port" not in settings
    assert settings["cors_allowed_origins"] == ["*"]
