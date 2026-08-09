"""FastAPI application factory for the local Praxis web adapter."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from praxis.api.errors import register_exception_handlers
from praxis.api.routes import catalog, files, session, terminal
from praxis.api.routes.terminal import terminal_websocket
from praxis.api.security import AppSecurity, LocalSecurityMiddleware
from praxis.registry import bootstrap_registry
from praxis.terminal.base import TerminalSession
from praxis.terminal.factory import create_terminal_session
from praxis.terminal.registry import TerminalRegistry
from praxis.terminal.tickets import TerminalTicketStore

# Default Vite dev origins (proxy keeps FE same-origin to Vite; Origin is forwarded).
DEFAULT_VITE_ORIGINS = (
    "http://127.0.0.1:5173",
    "http://localhost:5173",
)

TerminalFactory = Callable[..., Awaitable[TerminalSession]]


def create_app(
    *,
    security: AppSecurity | None = None,
    allow_vite_origins: bool = True,
    static_dir: Path | None = None,
    ticket_store: TerminalTicketStore | None = None,
    terminal_registry: TerminalRegistry | None = None,
    terminal_factory: TerminalFactory | None = None,
) -> FastAPI:
    """Create the local Praxis API application.

    Does not enable CORS. Browser access is same-origin via ``praxis app`` static
    hosting, or via the Vite dev proxy.
    """
    bootstrap_registry()
    extra = list(DEFAULT_VITE_ORIGINS) if allow_vite_origins else []
    if security is None:
        sec = AppSecurity.create(extra_origins=extra)
    elif extra:
        sec = AppSecurity(
            token=security.token,
            host=security.host,
            port=security.port,
            trusted_origins=frozenset(set(security.trusted_origins) | set(extra)),
        )
    else:
        sec = security

    registry = terminal_registry or TerminalRegistry()
    tickets = ticket_store or TerminalTicketStore()
    factory = terminal_factory or create_terminal_session

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            await registry.close_all()

    app = FastAPI(
        title="Praxis",
        version="0.1.0",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    app.state.security = sec
    app.state.ticket_store = tickets
    app.state.terminal_registry = registry
    app.state.terminal_factory = factory

    register_exception_handlers(app)
    app.add_middleware(LocalSecurityMiddleware, security=sec)

    app.include_router(catalog.router, prefix="/api")
    app.include_router(session.router, prefix="/api")
    app.include_router(files.router, prefix="/api")
    app.include_router(terminal.router, prefix="/api")
    app.add_api_websocket_route("/ws/terminal", terminal_websocket)

    if static_dir is not None and static_dir.is_dir():
        app.mount(
            "/",
            StaticFiles(directory=str(static_dir), html=True),
            name="frontend",
        )

    return app


def app_public_url(security: AppSecurity) -> str:
    """Browser launch URL with capability token in the fragment (not query)."""
    return f"http://{security.host}:{security.port}/#token={security.token}"


def vite_dev_url(security: AppSecurity, *, vite_port: int = 5173) -> str:
    """Vite HMR origin with the current per-launch token (same Origin allowlist)."""
    return f"http://127.0.0.1:{vite_port}/#token={security.token}"
