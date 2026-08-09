"""ASGI entrypoint for uvicorn --reload and programmatic launch."""

from __future__ import annotations

import os
from pathlib import Path

from praxis.api.app import create_app
from praxis.api.security import AppSecurity

_FRONTEND_DIST = Path(__file__).resolve().parents[3] / "frontend" / "dist"


def _security_from_env() -> AppSecurity:
    host = os.environ.get("PRAXIS_APP_HOST", "127.0.0.1")
    port = int(os.environ.get("PRAXIS_APP_PORT", "8765"))
    token = os.environ.get("PRAXIS_APP_TOKEN")
    return AppSecurity.create(host=host, port=port, token=token)


def build_app() -> object:
    static = _FRONTEND_DIST if _FRONTEND_DIST.is_dir() else None
    return create_app(security=_security_from_env(), static_dir=static)


# Uvicorn target: praxis.api.asgi:app
app = build_app()
