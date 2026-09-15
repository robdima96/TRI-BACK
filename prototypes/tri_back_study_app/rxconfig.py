import os
from pathlib import Path
from urllib.parse import urlparse

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


_public = _env_pref("TRI_BACK_PUBLIC_ACCESS", "TRI_BACK_PUBLIC_ACCESS").lower() in (
    "1",
    "true",
    "yes",
    "on",
)
_base = _env_pref("TRI_BACK_PUBLIC_BASE_URL", "TRI_BACK_PUBLIC_BASE_URL", "API_URL").rstrip(
    "/"
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

if not _public:
    # Pin local ports so Reflex does not auto-increment onto the bot (:8001).
    # Do not set frontend_port in public/Cloud Run: `reflex run --backend-only`
    # rejects --frontend-port.
    _config_kwargs["frontend_port"] = 3000
    _config_kwargs["backend_port"] = 8000
else:
    _config_kwargs["backend_port"] = 8000

if _public and _base:
    # Same public origin for UI + WebSocket via reverse proxy (never point at :8001).
    _config_kwargs["api_url"] = _base
    _config_kwargs["deploy_url"] = _base
    _config_kwargs["cors_allowed_origins"] = [
        _base,
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]
    host = urlparse(_base).hostname
    if host:
        _config_kwargs["vite_allowed_hosts"] = [host, "localhost", "127.0.0.1"]

config = rx.Config(**_config_kwargs)
