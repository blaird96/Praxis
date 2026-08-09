"""Terminal ticket + WebSocket lifecycle tests (fake PTY)."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from praxis import runner
from praxis.api.app import create_app
from praxis.api.security import TOKEN_HEADER, AppSecurity
from praxis.registry import bootstrap_registry, clear_registry
from praxis.terminal.fake import FakeTerminalSession
from praxis.terminal.tickets import TerminalTicketStore

ORIGIN = "http://127.0.0.1:8765"


@pytest.fixture(autouse=True)
def _registry(praxis_home: Path) -> None:
    clear_registry()
    bootstrap_registry()
    yield
    clear_registry()


@pytest.fixture
def security() -> AppSecurity:
    return AppSecurity.create(
        host="127.0.0.1",
        port=8765,
        token="test-capability-token",
        extra_origins=[ORIGIN, "http://127.0.0.1:5173"],
    )


@pytest.fixture
def fakes() -> list[FakeTerminalSession]:
    return []


@pytest.fixture
def ticket_store() -> TerminalTicketStore:
    return TerminalTicketStore(ttl_seconds=30)


@pytest.fixture
def client(
    security: AppSecurity,
    fakes: list[FakeTerminalSession],
    ticket_store: TerminalTicketStore,
) -> TestClient:
    async def factory(
        cwd: Path, *, cols: int = 80, rows: int = 24
    ) -> FakeTerminalSession:
        fake = FakeTerminalSession(cwd=cwd, cols=cols, rows=rows, output=b"welcome\r\n")
        fakes.append(fake)
        return fake

    app = create_app(
        security=security,
        allow_vite_origins=False,
        ticket_store=ticket_store,
        terminal_factory=factory,
    )
    return TestClient(app)


def _auth(security: AppSecurity) -> dict[str, str]:
    return {
        TOKEN_HEADER: security.token,
        "Host": "127.0.0.1:8765",
    }


def _ws_headers(origin: str = ORIGIN) -> dict[str, str]:
    return {"Host": "127.0.0.1:8765", "Origin": origin}


def test_ticket_requires_token_and_active_session(
    client: TestClient, security: AppSecurity
) -> None:
    missing_session = client.post("/api/terminal/ticket", headers=_auth(security))
    assert missing_session.status_code == 404

    runner.start("git", "merge-conflict")

    denied = client.post("/api/terminal/ticket", headers={"Host": "127.0.0.1:8765"})
    assert denied.status_code == 401

    ok = client.post("/api/terminal/ticket", headers=_auth(security))
    assert ok.status_code == 200
    body = ok.json()
    assert body["expires_in"] > 0
    assert body["session_id"]
    assert body["ticket"] != security.token
    assert len(body["ticket"]) >= 32


def test_ticket_single_use_and_expiry(security: AppSecurity, praxis_home: Path) -> None:
    store = TerminalTicketStore(ttl_seconds=0.05)
    fakes: list[FakeTerminalSession] = []

    async def factory(
        cwd: Path, *, cols: int = 80, rows: int = 24
    ) -> FakeTerminalSession:
        fake = FakeTerminalSession(cwd=cwd, cols=cols, rows=rows, output=b"welcome\r\n")
        fakes.append(fake)
        return fake

    app = create_app(
        security=security,
        allow_vite_origins=False,
        ticket_store=store,
        terminal_factory=factory,
    )
    client = TestClient(app)
    runner.start("git", "merge-conflict", home=praxis_home)

    first = client.post("/api/terminal/ticket", headers=_auth(security)).json()
    ticket = first["ticket"]

    with client.websocket_connect(
        f"/ws/terminal?ticket={ticket}", headers=_ws_headers()
    ) as ws:
        data = ws.receive_bytes()
        assert data == b"welcome\r\n"

    # Reuse rejected
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(
            f"/ws/terminal?ticket={ticket}", headers=_ws_headers()
        ):
            pass

    expired = client.post("/api/terminal/ticket", headers=_auth(security)).json()
    time.sleep(0.08)
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(
            f"/ws/terminal?ticket={expired['ticket']}", headers=_ws_headers()
        ):
            pass


def test_websocket_io_resize_and_cwd(
    client: TestClient,
    security: AppSecurity,
    fakes: list[FakeTerminalSession],
    praxis_home: Path,
) -> None:
    started = runner.start("git", "merge-conflict", home=praxis_home)
    ticket = client.post("/api/terminal/ticket", headers=_auth(security)).json()[
        "ticket"
    ]

    with client.websocket_connect(
        f"/ws/terminal?ticket={ticket}", headers=_ws_headers()
    ) as ws:
        assert ws.receive_bytes() == b"welcome\r\n"
        ws.send_text(json.dumps({"type": "input", "data": "git status\r"}))
        ws.send_text(json.dumps({"type": "resize", "cols": 120, "rows": 40}))
        ws.send_text(json.dumps({"type": "resize", "cols": 9999, "rows": 1}))
        err = json.loads(ws.receive_text())
        assert err["type"] == "error"
        assert "Invalid resize" in err["message"]
        # Malformed should not crash
        ws.send_text("not-json")
        bad = json.loads(ws.receive_text())
        assert bad["type"] == "error"

    assert len(fakes) == 1
    fake = fakes[0]
    assert fake.cwd == Path(started.repo_path).resolve()
    assert any(b"git status" in chunk for chunk in fake.written)
    assert (120, 40) in fake.resizes
    assert fake.closed()


def test_wrong_origin_rejected(
    client: TestClient, security: AppSecurity, praxis_home: Path
) -> None:
    runner.start("git", "merge-conflict", home=praxis_home)
    ticket = client.post("/api/terminal/ticket", headers=_auth(security)).json()[
        "ticket"
    ]
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(
            f"/ws/terminal?ticket={ticket}",
            headers=_ws_headers("http://evil.example"),
        ):
            pass


def test_invalid_ticket_rejected(client: TestClient) -> None:
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(
            "/ws/terminal?ticket=nope", headers=_ws_headers()
        ):
            pass


def test_reset_closes_pty(
    client: TestClient,
    security: AppSecurity,
    fakes: list[FakeTerminalSession],
    praxis_home: Path,
) -> None:
    runner.start("git", "merge-conflict", home=praxis_home)
    ticket = client.post("/api/terminal/ticket", headers=_auth(security)).json()[
        "ticket"
    ]
    with client.websocket_connect(
        f"/ws/terminal?ticket={ticket}", headers=_ws_headers()
    ) as ws:
        ws.receive_bytes()
        assert client.app.state.terminal_registry.connection_count() == 1
        reset = client.post("/api/session/reset", headers=_auth(security))
        assert reset.status_code == 200
        assert fakes[0].closed()
        assert client.app.state.terminal_registry.connection_count() == 0


def test_ticket_binds_original_session(
    client: TestClient, security: AppSecurity, praxis_home: Path, fakes: list
) -> None:
    first = runner.start("git", "merge-conflict", home=praxis_home)
    ticket_body = client.post("/api/terminal/ticket", headers=_auth(security)).json()
    assert ticket_body["session_id"] == first.session.session_id

    # Start a new session (previous retained); ticket still binds first session.
    second = runner.start("git", "merge-conflict", home=praxis_home)
    assert second.session.session_id != first.session.session_id

    with client.websocket_connect(
        f"/ws/terminal?ticket={ticket_body['ticket']}", headers=_ws_headers()
    ) as ws:
        ws.receive_bytes()
    assert fakes[0].cwd == Path(first.session.repo_path).resolve()
