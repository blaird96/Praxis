"""Terminal ticket HTTP endpoint and WebSocket PTY bridge.

Protocol
--------
Client → server (JSON text)::

    {"type": "input", "data": "<utf-8 string>"}
    {"type": "resize", "cols": 120, "rows": 30}

Client → server (optional binary frames): raw stdin bytes.

Server → client (binary frames): raw PTY/ConPTY output (ANSI preserved).

Server → client (JSON text)::

    {"type": "exit", "code": 0}
    {"type": "error", "message": "..."}
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import secrets
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect

from praxis import runner
from praxis.api.schemas import TerminalTicketResponse
from praxis.api.security import AppSecurity
from praxis.session import load_session_by_id
from praxis.terminal.base import (
    DEFAULT_COLS,
    DEFAULT_ROWS,
    MAX_COLS,
    MAX_ROWS,
    MIN_COLS,
    MIN_ROWS,
    TerminalSession,
)
from praxis.terminal.factory import TerminalSpawnError
from praxis.terminal.registry import TerminalRegistry, TrackedTerminal
from praxis.terminal.tickets import TerminalTicketError, TerminalTicketStore
from praxis.workspace import assert_safe_repo_path

logger = logging.getLogger(__name__)

router = APIRouter(tags=["terminal"])

TerminalFactory = Callable[..., Awaitable[TerminalSession]]


@router.post("/terminal/ticket", response_model=TerminalTicketResponse)
def issue_terminal_ticket(request: Request) -> TerminalTicketResponse:
    """Issue a short-lived, single-use ticket for the active session's terminal."""
    session = runner.require_active_session()
    store: TerminalTicketStore = request.app.state.ticket_store
    ticket = store.issue(session.session_id)
    return TerminalTicketResponse(
        ticket=ticket.ticket,
        expires_in=int(store.ttl_seconds),
        session_id=ticket.session_id,
    )


def _validate_resize(cols: Any, rows: Any) -> tuple[int, int] | None:
    try:
        c = int(cols)
        r = int(rows)
    except (TypeError, ValueError):
        return None
    if not (MIN_COLS <= c <= MAX_COLS and MIN_ROWS <= r <= MAX_ROWS):
        return None
    return c, r


async def _safe_send_json(websocket: WebSocket, payload: dict[str, Any]) -> None:
    with contextlib.suppress(Exception):
        await websocket.send_text(json.dumps(payload))


async def _safe_send_bytes(websocket: WebSocket, data: bytes) -> None:
    with contextlib.suppress(Exception):
        await websocket.send_bytes(data)


async def terminal_websocket(websocket: WebSocket) -> None:
    """Bridge xterm.js to a real PTY bound to a ticket's Praxis session."""
    app = websocket.app
    security: AppSecurity = app.state.security
    store: TerminalTicketStore = app.state.ticket_store
    registry: TerminalRegistry = app.state.terminal_registry
    factory: TerminalFactory = app.state.terminal_factory

    host = websocket.headers.get("host", "")
    if host not in security.expected_hosts:
        await websocket.close(code=1008, reason="Invalid Host")
        return

    origin = websocket.headers.get("origin")
    if origin is None or origin not in security.trusted_origins:
        await websocket.close(code=1008, reason="Invalid Origin")
        return

    ticket_value = websocket.query_params.get("ticket")
    if not ticket_value:
        await websocket.close(code=1008, reason="Missing ticket")
        return

    try:
        ticket = store.consume(ticket_value)
    except TerminalTicketError as exc:
        await websocket.close(code=1008, reason=exc.message[:120])
        return

    try:
        session = load_session_by_id(ticket.session_id)
        repo = assert_safe_repo_path(
            Path(session.workspace_path), Path(session.repo_path)
        )
    except Exception as exc:
        await websocket.close(code=1011, reason=str(exc)[:120])
        return

    await websocket.accept()
    connection_id = secrets.token_hex(8)

    try:
        terminal = await factory(repo, cols=DEFAULT_COLS, rows=DEFAULT_ROWS)
    except TerminalSpawnError as exc:
        await _safe_send_json(websocket, {"type": "error", "message": exc.message})
        await websocket.close(code=1011, reason="spawn failed")
        return
    except Exception as exc:
        logger.exception("terminal spawn failed")
        await _safe_send_json(
            websocket,
            {"type": "error", "message": f"Failed to start terminal: {exc}"},
        )
        await websocket.close(code=1011, reason="spawn failed")
        return

    tracked = TrackedTerminal(
        connection_id=connection_id,
        session_id=session.session_id,
        terminal=terminal,
    )
    await registry.register(tracked)

    async def pump_output() -> None:
        exit_code = 0
        try:
            while not terminal.closed():
                data = await terminal.read()
                if not data:
                    break
                await _safe_send_bytes(websocket, data)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.debug("terminal output pump ended", exc_info=True)
        finally:
            try:
                if not terminal.closed():
                    exit_code = await asyncio.wait_for(
                        asyncio.shield(terminal.wait()), timeout=0.5
                    )
            except (TimeoutError, asyncio.CancelledError):
                exit_code = -1
            except Exception:
                exit_code = -1
            await _safe_send_json(websocket, {"type": "exit", "code": exit_code})

    output_task = asyncio.create_task(pump_output())
    tracked.tasks.append(output_task)

    try:
        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                break
            text = message.get("text")
            raw = message.get("bytes")
            if text is not None:
                try:
                    payload = json.loads(text)
                except json.JSONDecodeError:
                    await _safe_send_json(
                        websocket,
                        {"type": "error", "message": "Malformed terminal message"},
                    )
                    continue
                if not isinstance(payload, dict):
                    continue
                msg_type = payload.get("type")
                if msg_type == "input":
                    data = payload.get("data", "")
                    if isinstance(data, str) and data:
                        await terminal.write(data.encode("utf-8"))
                elif msg_type == "resize":
                    size = _validate_resize(payload.get("cols"), payload.get("rows"))
                    if size is None:
                        await _safe_send_json(
                            websocket,
                            {
                                "type": "error",
                                "message": (
                                    f"Invalid resize; cols {MIN_COLS}-{MAX_COLS}, "
                                    f"rows {MIN_ROWS}-{MAX_ROWS}"
                                ),
                            },
                        )
                        continue
                    cols, rows = size
                    await terminal.resize(cols, rows)
                else:
                    await _safe_send_json(
                        websocket,
                        {
                            "type": "error",
                            "message": f"Unknown message type: {msg_type!r}",
                        },
                    )
            elif raw is not None:
                await terminal.write(raw)
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.debug("terminal websocket ended", exc_info=True)
    finally:
        await registry.close_connection(connection_id)
        with contextlib.suppress(Exception):
            await websocket.close()
