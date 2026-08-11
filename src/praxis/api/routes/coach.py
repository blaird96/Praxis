"""OpenAI coaching REST endpoints and ticket issuance.

The token-by-token chat streaming itself happens over `ws /ws/coach` (see
`coach_websocket` below), authenticated the same way as the terminal: a
short-lived, single-use ticket obtained from `POST /api/coach/ticket`.
"""

from __future__ import annotations

import contextlib
import json
import logging
from typing import Any

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect

from praxis import runner
from praxis.api.schemas import (
    CoachKeyRequest,
    CoachStatusResponse,
    CoachTestResponse,
    CoachTicketResponse,
)
from praxis.api.security import AppSecurity
from praxis.coaching.coach import CoachApiError, build_system_prompt, stream_chat
from praxis.coaching.coach import test_connection as coach_test_connection
from praxis.coaching.prefs import load_coaching_prefs
from praxis.coaching.secrets_store import (
    CoachingConfigError,
    remove_api_key,
    resolve_api_key,
    store_api_key,
)
from praxis.errors import PraxisError
from praxis.registry import get_scenario
from praxis.runner import CheckOutcome
from praxis.session import load_session_by_id
from praxis.terminal.tickets import TerminalTicketError, TerminalTicketStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/coach", tags=["coach"])

MAX_HISTORY_MESSAGES = 20
MAX_MESSAGE_CHARS = 4000


def _status() -> CoachStatusResponse:
    resolved = resolve_api_key()
    prefs = load_coaching_prefs()
    return CoachStatusResponse(
        configured=resolved is not None,
        source=resolved[1] if resolved else None,
        model=prefs.model,
    )


@router.get("/status", response_model=CoachStatusResponse)
def get_status() -> CoachStatusResponse:
    return _status()


@router.post("/key", response_model=CoachStatusResponse)
async def configure_key(body: CoachKeyRequest) -> CoachStatusResponse:
    api_key = body.api_key.strip()
    if not api_key:
        raise PraxisError("API key must not be empty")
    prefs = load_coaching_prefs()
    # Fail fast: don't persist a key that doesn't actually work.
    await coach_test_connection(api_key, prefs.model)
    store_api_key(api_key)
    return _status()


@router.delete("/key", response_model=CoachStatusResponse)
def remove_key() -> CoachStatusResponse:
    remove_api_key()
    return _status()


@router.post("/test", response_model=CoachTestResponse)
async def test_connection_route() -> CoachTestResponse:
    resolved = resolve_api_key()
    if resolved is None:
        return CoachTestResponse(ok=False, detail="OpenAI is not configured yet.")
    api_key, _source = resolved
    prefs = load_coaching_prefs()
    try:
        await coach_test_connection(api_key, prefs.model)
    except CoachApiError as exc:
        return CoachTestResponse(ok=False, detail=exc.message)
    return CoachTestResponse(ok=True, detail=None)


@router.post("/ticket", response_model=CoachTicketResponse)
def issue_coach_ticket(request: Request) -> CoachTicketResponse:
    session = runner.require_active_session()
    store: TerminalTicketStore = request.app.state.coach_ticket_store
    ticket = store.issue(session.session_id)
    return CoachTicketResponse(
        ticket=ticket.ticket,
        expires_in=int(store.ttl_seconds),
        session_id=ticket.session_id,
    )


async def _safe_send_json(websocket: WebSocket, payload: dict[str, Any]) -> None:
    with contextlib.suppress(Exception):
        await websocket.send_text(json.dumps(payload))


def _clip_history(history: Any) -> list[dict[str, str]]:
    """Bound token usage: keep the last N messages, each capped in length."""
    if not isinstance(history, list):
        return []
    clipped: list[dict[str, str]] = []
    for item in history[-MAX_HISTORY_MESSAGES:]:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        content = item.get("content")
        if role not in ("user", "assistant") or not isinstance(content, str):
            continue
        clipped.append({"role": role, "content": content[:MAX_MESSAGE_CHARS]})
    return clipped


async def coach_websocket(websocket: WebSocket) -> None:
    """Ticket-authenticated streaming chat, mirroring `terminal_websocket`."""
    app = websocket.app
    security: AppSecurity = app.state.security
    store: TerminalTicketStore = app.state.coach_ticket_store

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
    except Exception as exc:
        await websocket.close(code=1011, reason=str(exc)[:120])
        return

    await websocket.accept()

    try:
        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                break
            text = message.get("text")
            if text is None:
                continue
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                await _safe_send_json(
                    websocket, {"type": "error", "message": "Malformed message"}
                )
                continue
            if not isinstance(payload, dict) or payload.get("type") != "message":
                continue

            content = payload.get("content")
            if not isinstance(content, str) or not content.strip():
                continue

            resolved = resolve_api_key()
            if resolved is None:
                await _safe_send_json(
                    websocket,
                    {
                        "type": "error",
                        "message": (
                            "OpenAI is not configured. Add an API key in Settings."
                        ),
                    },
                )
                continue
            api_key, _source = resolved
            prefs = load_coaching_prefs()

            try:
                scenario = get_scenario(session.module, session.scenario)
                assignment = scenario.assignment()
                outcome: CheckOutcome | None
                try:
                    outcome = runner.check_active()
                except PraxisError:
                    outcome = None
                system_prompt = build_system_prompt(
                    assignment,
                    session.module,
                    session.scenario,
                    getattr(scenario, "difficulty", None),
                    list(getattr(scenario, "concepts", []) or []),
                    outcome.result if outcome else None,
                )
            except Exception as exc:
                await _safe_send_json(
                    websocket,
                    {"type": "error", "message": f"Could not build context: {exc}"},
                )
                continue

            history = _clip_history(payload.get("history"))
            messages = [
                {"role": "system", "content": system_prompt},
                *history,
                {"role": "user", "content": content[:MAX_MESSAGE_CHARS]},
            ]

            try:
                async for delta in stream_chat(api_key, prefs.model, messages):
                    await websocket.send_text(
                        json.dumps({"type": "delta", "content": delta})
                    )
                await _safe_send_json(websocket, {"type": "done"})
            except CoachApiError as exc:
                await _safe_send_json(
                    websocket, {"type": "error", "message": exc.message}
                )
            except CoachingConfigError as exc:
                await _safe_send_json(
                    websocket, {"type": "error", "message": exc.message}
                )
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.debug("coach websocket ended", exc_info=True)
    finally:
        with contextlib.suppress(Exception):
            await websocket.close()
