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

_public = os.getenv("DIGIMSK_PUBLIC_ACCESS", "").strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
)
_base = (os.getenv("DIGIMSK_PUBLIC_BASE_URL") or os.getenv("API_URL") or "").strip().rstrip(
    "/"
)

_config_kwargs: dict = {
    "app_name": "digimsk_study_app",
    # Pin local ports so Reflex does not auto-increment onto the bot (:8001).
    "frontend_port": 3000,
    "backend_port": 8000,
    "plugins": [
        RadixThemesPlugin(
            theme=rx.theme(accent_color="blue", appearance="light", has_background=False),
        ),
    ],
    "disable_plugins": [SitemapPlugin],
}

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
