"""Study-app test defaults. Admin password is required; never use a source fallback."""

from __future__ import annotations

import os

os.environ.setdefault("TRI_BACK_ADMIN_PASSWORD", "test-admin-password")
