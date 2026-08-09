"""Local process security controls for the Praxis web adapter."""

from __future__ import annotations

import secrets
from dataclasses import dataclass, field

from fastapi import Header, HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

TOKEN_HEADER = "X-Praxis-Token"
TOKEN_QUERY = "token"


@dataclass(slots=True)
class AppSecurity:
    """Per-launch local capability settings (not user authentication)."""

    token: str
    host: str = "127.0.0.1"
    port: int = 8765
    trusted_origins: frozenset[str] = field(default_factory=frozenset)

    @classmethod
    def create(
        cls,
        *,
        host: str = "127.0.0.1",
        port: int = 8765,
        token: str | None = None,
        extra_origins: list[str] | None = None,
    ) -> AppSecurity:
        origins = {
            f"http://{host}:{port}",
            f"http://127.0.0.1:{port}",
            f"http://localhost:{port}",
        }
        if extra_origins:
            origins.update(extra_origins)
        return cls(
            token=token or secrets.token_urlsafe(32),
            host=host,
            port=port,
            trusted_origins=frozenset(origins),
        )

    @property
    def expected_hosts(self) -> frozenset[str]:
        return frozenset(
            {
                f"{self.host}:{self.port}",
                f"127.0.0.1:{self.port}",
                f"localhost:{self.port}",
            }
        )


def _extract_token(request: Request) -> str | None:
    header = request.headers.get(TOKEN_HEADER)
    if header:
        return header.strip()
    return request.query_params.get(TOKEN_QUERY)


class LocalSecurityMiddleware(BaseHTTPMiddleware):
    """Enforce Host / Origin / capability token for /api routes."""

    def __init__(self, app: ASGIApp, security: AppSecurity) -> None:
        super().__init__(app)
        self.security = security

    async def dispatch(self, request: Request, call_next: object) -> Response:
        path = request.url.path
        if not path.startswith("/api"):
            return await call_next(request)  # type: ignore[misc]

        # Health is unauthenticated for simple probes; still require Host.
        host = request.headers.get("host", "")
        if host not in self.security.expected_hosts:
            return JSONResponse(
                status_code=400,
                content={
                    "detail": f"Invalid Host header: {host!r}",
                    "code": "invalid_host",
                },
            )

        if path == "/api/health":
            return await call_next(request)  # type: ignore[misc]

        origin = request.headers.get("origin")
        if origin is not None and origin not in self.security.trusted_origins:
            return JSONResponse(
                status_code=403,
                content={
                    "detail": f"Origin not allowed: {origin!r}",
                    "code": "invalid_origin",
                },
            )

        token = _extract_token(request)
        if not token or not secrets.compare_digest(token, self.security.token):
            return JSONResponse(
                status_code=401,
                content={
                    "detail": "Missing or invalid Praxis capability token",
                    "code": "invalid_token",
                },
            )

        return await call_next(request)  # type: ignore[misc]


def require_capability_token(
    request: Request,
    x_praxis_token: str | None = Header(default=None, alias=TOKEN_HEADER),
) -> str:
    """Dependency for routes that need an explicit token check (tests/helpers)."""
    security: AppSecurity = request.app.state.security
    token = x_praxis_token or request.query_params.get(TOKEN_QUERY)
    if not token or not secrets.compare_digest(token, security.token):
        raise HTTPException(
            status_code=401,
            detail="Missing or invalid Praxis capability token",
        )
    return token
