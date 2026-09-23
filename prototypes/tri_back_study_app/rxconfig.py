import os
from pathlib import Path

import reflex as rx
from reflex_base.plugins.sitemap import SitemapPlugin
from reflex_components_radix.plugin import RadixThemesPlugin

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent / ".env", override=False)
except ImportError:
    pass


def _env_pref(*names: str) -> str:
    """First non-empty env among names; TRI_BACK_* callers should also pass TRI_BACK_*."""
    for name in names:
        val = (os.getenv(name) or "").strip()
        if val:
            return val
    return ""


def public_reflex_settings(*, public: bool) -> dict:
    """Local ports, or same-origin API URL for the Cloud Run / Caddy export.

    Public mode must not bake a hostname into ``api_url``. The browser already
    opened the study host; Caddy proxies ``/_event`` on that same origin.
    """
    if not public:
        return {
            "frontend_port": 3000,
            "backend_port": 8000,
        }
    return {
        "backend_port": 8000,
        "api_url": "",
        "deploy_url": "",
        "cors_allowed_origins": ["*"],
    }


_public = _env_pref("TRI_BACK_PUBLIC_ACCESS", "TRI_BACK_PUBLIC_ACCESS").lower() in (
    "1",
    "true",
    "yes",
    "on",
)

_config_kwargs: dict = {
    "app_name": "tri_back_study_app",
    "plugins": [
        RadixThemesPlugin(
            theme=rx.theme(accent_color="blue", appearance="light", has_background=False),
        ),
    ],
    "disable_plugins": [SitemapPlugin],
}
_config_kwargs.update(public_reflex_settings(public=_public))

config = rx.Config(**_config_kwargs)
