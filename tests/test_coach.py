"""Coach REST + websocket tests (all OpenAI calls are stubbed, no real network)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import keyring.errors
import pytest
from fastapi.testclient import TestClient

from praxis import runner
from praxis.api.app import create_app
from praxis.api.routes import coach as coach_routes
from praxis.api.security import TOKEN_HEADER, AppSecurity
from praxis.coaching import secrets_store
from praxis.coaching.coach import CoachApiError
from praxis.registry import bootstrap_registry, clear_registry


@pytest.fixture(autouse=True)
def _registry(praxis_home: Path) -> None:
    clear_registry()
    bootstrap_registry()
    yield
    clear_registry()


@pytest.fixture(autouse=True)
def _no_real_openai_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    """Guard against accidentally hitting the real network in this file."""
    monkeypatch.delenv(secrets_store.ENV_VAR, raising=False)


class _FakeKeyring:
    """In-memory stand-in for the `keyring` module's password functions."""

    def __init__(self) -> None:
        self._passwords: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        return self._passwords.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self._passwords[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        key = (service, username)
        if key not in self._passwords:
            raise keyring.errors.PasswordDeleteError("not found")
        del self._passwords[key]


@pytest.fixture(autouse=True)
def _isolated_keyring(monkeypatch: pytest.MonkeyPatch) -> None:
    """Never read/write the developer's real OS credential store from tests."""
    fake = _FakeKeyring()
    monkeypatch.setattr(secrets_store.keyring, "get_password", fake.get_password)
    monkeypatch.setattr(secrets_store.keyring, "set_password", fake.set_password)
    monkeypatch.setattr(secrets_store.keyring, "delete_password", fake.delete_password)


@pytest.fixture
def security() -> AppSecurity:
    return AppSecurity.create(
        host="127.0.0.1",
        port=8765,
        token="test-capability-token",
        extra_origins=["http://127.0.0.1:5173"],
    )


@pytest.fixture
def client(security: AppSecurity) -> TestClient:
    app = create_app(security=security, allow_vite_origins=False)
    return TestClient(app)


def _auth(security: AppSecurity) -> dict[str, str]:
    return {TOKEN_HEADER: security.token, "Host": "127.0.0.1:8765"}


def test_status_reports_unconfigured_by_default(
    client: TestClient, security: AppSecurity
) -> None:
    response = client.get("/api/coach/status", headers=_auth(security))
    assert response.status_code == 200
    body = response.json()
    assert body["configured"] is False
    assert body["source"] is None
    assert body["model"]


def test_status_reports_env_source(
    client: TestClient, security: AppSecurity, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(secrets_store.ENV_VAR, "sk-from-env")
    response = client.get("/api/coach/status", headers=_auth(security))
    body = response.json()
    assert body["configured"] is True
    assert body["source"] == "env"


def test_configure_key_tests_connection_before_storing(
    client: TestClient, security: AppSecurity, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []

    async def fake_test_connection(api_key: str, model: str) -> None:
        calls.append(api_key)

    stored: dict[str, str] = {}
    monkeypatch.setattr(coach_routes, "coach_test_connection", fake_test_connection)
    monkeypatch.setattr(
        coach_routes, "store_api_key", lambda key: stored.setdefault("key", key)
    )
    monkeypatch.setattr(
        coach_routes,
        "resolve_api_key",
        lambda: (stored["key"], "keyring") if "key" in stored else None,
    )

    response = client.post(
        "/api/coach/key",
        headers=_auth(security),
        json={"api_key": "sk-good-key"},
    )
    assert response.status_code == 200
    assert response.json()["configured"] is True
    assert calls == ["sk-good-key"]
    assert stored["key"] == "sk-good-key"


def test_configure_key_rejects_invalid_key_without_storing(
    client: TestClient, security: AppSecurity, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def failing_test_connection(api_key: str, model: str) -> None:
        raise CoachApiError("OpenAI request failed (401): invalid api key")

    stored_calls: list[str] = []
    monkeypatch.setattr(coach_routes, "coach_test_connection", failing_test_connection)
    monkeypatch.setattr(
        coach_routes, "store_api_key", lambda key: stored_calls.append(key)
    )

    response = client.post(
        "/api/coach/key",
        headers=_auth(security),
        json={"api_key": "sk-bad-key"},
    )
    assert response.status_code == 400
    assert response.json()["code"] == "praxis_error"
    assert stored_calls == []


def test_remove_key_and_status_round_trip(
    client: TestClient, security: AppSecurity, monkeypatch: pytest.MonkeyPatch
) -> None:
    removed: list[bool] = []
    monkeypatch.setattr(coach_routes, "remove_api_key", lambda: removed.append(True))

    response = client.delete("/api/coach/key", headers=_auth(security))
    assert response.status_code == 200
    assert removed == [True]
    assert response.json()["configured"] is False


def test_test_connection_route_when_unconfigured(
    client: TestClient, security: AppSecurity
) -> None:
    response = client.post("/api/coach/test", headers=_auth(security))
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert "not configured" in body["detail"].lower()


def test_test_connection_route_success(
    client: TestClient, security: AppSecurity, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(secrets_store.ENV_VAR, "sk-env-key")

    async def ok_test_connection(api_key: str, model: str) -> None:
        return None

    monkeypatch.setattr(coach_routes, "coach_test_connection", ok_test_connection)

    response = client.post("/api/coach/test", headers=_auth(security))
    assert response.status_code == 200
    assert response.json() == {"ok": True, "detail": None}


def test_test_connection_route_failure(
    client: TestClient, security: AppSecurity, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(secrets_store.ENV_VAR, "sk-env-key")

    async def failing_test_connection(api_key: str, model: str) -> None:
        raise CoachApiError("boom")

    monkeypatch.setattr(coach_routes, "coach_test_connection", failing_test_connection)

    response = client.post("/api/coach/test", headers=_auth(security))
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert body["detail"] == "boom"


def test_ticket_requires_active_session(
    client: TestClient, security: AppSecurity
) -> None:
    response = client.post("/api/coach/ticket", headers=_auth(security))
    assert response.status_code == 404


def test_ticket_issued_for_active_session(
    client: TestClient, security: AppSecurity, praxis_home: Path
) -> None:
    runner.start("git", "merge-conflict", home=praxis_home)
    response = client.post("/api/coach/ticket", headers=_auth(security))
    assert response.status_code == 200
    body = response.json()
    assert body["session_id"]
    assert body["expires_in"] > 0


def test_websocket_rejects_missing_ticket(
    client: TestClient, security: AppSecurity, praxis_home: Path
) -> None:
    runner.start("git", "merge-conflict", home=praxis_home)
    with pytest.raises(Exception):  # noqa: B017 - starlette raises on 1008 close
        with client.websocket_connect(
            "/ws/coach",
            headers={"Host": "127.0.0.1:8765", "Origin": "http://127.0.0.1:8765"},
        ):
            pass


def test_websocket_streams_deltas_when_configured(
    client: TestClient,
    security: AppSecurity,
    praxis_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner.start("git", "merge-conflict", home=praxis_home)
    ticket_resp = client.post("/api/coach/ticket", headers=_auth(security))
    ticket = ticket_resp.json()["ticket"]

    monkeypatch.setenv(secrets_store.ENV_VAR, "sk-env-key")

    async def fake_stream_chat(
        api_key: str, model: str, messages: list[dict[str, str]]
    ) -> AsyncIterator[str]:
        assert messages[0]["role"] == "system"
        for chunk in ["Hel", "lo!"]:
            yield chunk

    monkeypatch.setattr(coach_routes, "stream_chat", fake_stream_chat)

    with client.websocket_connect(
        f"/ws/coach?ticket={ticket}",
        headers={"Host": "127.0.0.1:8765", "Origin": "http://127.0.0.1:8765"},
    ) as ws:
        ws.send_json({"type": "message", "content": "help me", "history": []})
        first = ws.receive_json()
        second = ws.receive_json()
        done = ws.receive_json()

    assert first == {"type": "delta", "content": "Hel"}
    assert second == {"type": "delta", "content": "lo!"}
    assert done == {"type": "done"}


def test_websocket_errors_when_not_configured(
    client: TestClient,
    security: AppSecurity,
    praxis_home: Path,
) -> None:
    runner.start("git", "merge-conflict", home=praxis_home)
    ticket_resp = client.post("/api/coach/ticket", headers=_auth(security))
    ticket = ticket_resp.json()["ticket"]

    with client.websocket_connect(
        f"/ws/coach?ticket={ticket}",
        headers={"Host": "127.0.0.1:8765", "Origin": "http://127.0.0.1:8765"},
    ) as ws:
        ws.send_json({"type": "message", "content": "help me", "history": []})
        error = ws.receive_json()

    assert error["type"] == "error"
    assert "not configured" in error["message"].lower()


def test_ticket_is_single_use(
    client: TestClient, security: AppSecurity, praxis_home: Path
) -> None:
    runner.start("git", "merge-conflict", home=praxis_home)
    ticket = client.post("/api/coach/ticket", headers=_auth(security)).json()["ticket"]

    with client.websocket_connect(
        f"/ws/coach?ticket={ticket}",
        headers={"Host": "127.0.0.1:8765", "Origin": "http://127.0.0.1:8765"},
    ):
        pass

    with pytest.raises(Exception):  # noqa: B017 - starlette raises on 1008 close
        with client.websocket_connect(
            f"/ws/coach?ticket={ticket}",
            headers={"Host": "127.0.0.1:8765", "Origin": "http://127.0.0.1:8765"},
        ):
            pass
