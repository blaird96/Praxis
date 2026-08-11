"""API adapter tests (active session + localhost security)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from praxis import runner
from praxis.api.app import create_app
from praxis.api.security import TOKEN_HEADER, AppSecurity
from praxis.registry import bootstrap_registry, clear_registry


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
        extra_origins=["http://127.0.0.1:5173"],
    )


@pytest.fixture
def client(security: AppSecurity) -> TestClient:
    app = create_app(security=security, allow_vite_origins=False)
    return TestClient(app)


def _auth(security: AppSecurity) -> dict[str, str]:
    return {
        TOKEN_HEADER: security.token,
        "Host": "127.0.0.1:8765",
    }


def test_health_requires_valid_host_but_not_token(client: TestClient) -> None:
    bad = client.get("/api/health", headers={"Host": "evil.example:8765"})
    assert bad.status_code == 400
    assert bad.json()["code"] == "invalid_host"

    ok = client.get("/api/health", headers={"Host": "127.0.0.1:8765"})
    assert ok.status_code == 200
    assert ok.json()["status"] == "ok"


def test_catalog_requires_token(client: TestClient, security: AppSecurity) -> None:
    denied = client.get("/api/catalog", headers={"Host": "127.0.0.1:8765"})
    assert denied.status_code == 401

    ok = client.get("/api/catalog", headers=_auth(security))
    assert ok.status_code == 200
    body = ok.json()
    module_ids = [m["id"] for m in body["modules"]]
    assert "git" in module_ids
    assert "docker" in module_ids
    assert "kubernetes" in module_ids
    git = next(m for m in body["modules"] if m["id"] == "git")
    assert any(s["id"] == "merge-conflict" for s in git["scenarios"])
    assert any(s.get("concepts") for s in git["scenarios"])
    k8s = next(m for m in body["modules"] if m["id"] == "kubernetes")
    assert "available" in k8s


def test_rejects_untrusted_origin(client: TestClient, security: AppSecurity) -> None:
    response = client.get(
        "/api/catalog",
        headers={
            **_auth(security),
            "Origin": "http://evil.example",
        },
    )
    assert response.status_code == 403
    assert response.json()["code"] == "invalid_origin"


def test_allows_trusted_vite_origin_when_enabled(security: AppSecurity) -> None:
    app = create_app(security=security, allow_vite_origins=True)
    client = TestClient(app)
    response = client.get(
        "/api/catalog",
        headers={
            **_auth(security),
            "Origin": "http://127.0.0.1:5173",
        },
    )
    assert response.status_code == 200


def test_session_and_check_active_only(
    client: TestClient, security: AppSecurity, praxis_home: Path
) -> None:
    missing = client.get("/api/session", headers=_auth(security))
    assert missing.status_code == 404

    runner.start("git", "merge-conflict", home=praxis_home)

    session = client.get("/api/session", headers=_auth(security))
    assert session.status_code == 200
    payload = session.json()
    assert payload["module"] == "git"
    assert payload["scenario"] == "merge-conflict"
    assert payload["assignment"]["title"]
    assert payload["check"] is None

    checked = client.post("/api/session/check", headers=_auth(security))
    assert checked.status_code == 200
    result = checked.json()["check"]
    assert result is not None
    assert result["passed"] is False
    by_id = {item["id"]: item["passed"] for item in result["objectives"]}
    assert by_id["on-main"] is True
    assert by_id["no-markers"] is False


def test_check_active_ignores_process_cwd(
    client: TestClient,
    security: AppSecurity,
    praxis_home: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner.start("git", "merge-conflict", home=praxis_home)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)

    checked = client.post("/api/session/check", headers=_auth(security))
    assert checked.status_code == 200
    assert checked.json()["check"]["passed"] is False


def test_no_cors_wildcard_headers(client: TestClient, security: AppSecurity) -> None:
    response = client.get("/api/catalog", headers=_auth(security))
    assert response.status_code == 200
    assert "access-control-allow-origin" not in {k.lower() for k in response.headers}


def test_catalog_includes_presentation_metadata(
    client: TestClient, security: AppSecurity
) -> None:
    response = client.get("/api/catalog", headers=_auth(security))
    assert response.status_code == 200
    git = next(m for m in response.json()["modules"] if m["id"] == "git")
    scenario = next(s for s in git["scenarios"] if s["id"] == "merge-conflict")
    assert scenario["title"]
    assert scenario["description"]
    assert scenario["difficulty"] == "beginner"
    assert "merge" in scenario["concepts"]
    assert scenario["completed"] is False


def test_catalog_completed_flag_toggles_after_a_passing_check(
    client: TestClient, security: AppSecurity, praxis_home: Path
) -> None:
    from praxis.progress import record_check_result

    before = client.get("/api/catalog", headers=_auth(security))
    git = next(m for m in before.json()["modules"] if m["id"] == "git")
    scenario = next(s for s in git["scenarios"] if s["id"] == "merge-conflict")
    assert scenario["completed"] is False

    record_check_result("git", "merge-conflict", True, home=praxis_home)

    after = client.get("/api/catalog", headers=_auth(security))
    git = next(m for m in after.json()["modules"] if m["id"] == "git")
    scenario = next(s for s in git["scenarios"] if s["id"] == "merge-conflict")
    assert scenario["completed"] is True


def test_start_success_persists_and_activates(
    client: TestClient, security: AppSecurity, praxis_home: Path
) -> None:
    response = client.post(
        "/api/session/start",
        headers=_auth(security),
        json={"module": "git", "scenario": "merge-conflict"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["module"] == "git"
    assert body["scenario"] == "merge-conflict"
    assert body["previous_session_id"] is None
    assert body["check"] is not None
    assert body["check"]["passed"] is False

    from praxis.session import load_global_state, load_scenario_state

    state = load_global_state(praxis_home)
    assert state.active_session_id == body["session_id"]
    workspace = praxis_home / "workspaces" / body["session_id"]
    raw = load_scenario_state(workspace)
    assert raw is not None
    assert "main_tip_sha" in raw


def test_start_unknown_module_and_scenario(
    client: TestClient, security: AppSecurity
) -> None:
    unknown_module = client.post(
        "/api/session/start",
        headers=_auth(security),
        json={"module": "missing-mod", "scenario": "basic"},
    )
    assert unknown_module.status_code == 404
    assert unknown_module.json()["code"] == "unknown_module"

    unknown_scenario = client.post(
        "/api/session/start",
        headers=_auth(security),
        json={"module": "git", "scenario": "rebase"},
    )
    assert unknown_scenario.status_code == 404
    assert unknown_scenario.json()["code"] == "unknown_scenario"


def test_start_setup_failure_preserves_active(
    client: TestClient,
    security: AppSecurity,
    praxis_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = client.post(
        "/api/session/start",
        headers=_auth(security),
        json={"module": "git", "scenario": "merge-conflict"},
    )
    assert first.status_code == 200
    previous = first.json()["session_id"]

    from praxis.errors import ScenarioSetupError
    from praxis.modules.git.scenarios.merge_conflict import MergeConflictScenario

    def boom(self: MergeConflictScenario, repo_path: Path) -> object:
        raise ScenarioSetupError("forced setup failure")

    monkeypatch.setattr(MergeConflictScenario, "setup", boom)
    clear_registry()
    bootstrap_registry()

    failed = client.post(
        "/api/session/start",
        headers=_auth(security),
        json={"module": "git", "scenario": "merge-conflict"},
    )
    assert failed.status_code == 400
    assert "forced setup failure" in failed.json()["detail"]

    from praxis.session import load_global_state

    assert load_global_state(praxis_home).active_session_id == previous


def test_start_requires_token_and_rejects_bad_host_origin(
    client: TestClient, security: AppSecurity
) -> None:
    no_token = client.post(
        "/api/session/start",
        headers={"Host": "127.0.0.1:8765"},
        json={"module": "git", "scenario": "merge-conflict"},
    )
    assert no_token.status_code == 401

    bad_host = client.post(
        "/api/session/start",
        headers={TOKEN_HEADER: security.token, "Host": "evil:8765"},
        json={"module": "git", "scenario": "merge-conflict"},
    )
    assert bad_host.status_code == 400
    assert bad_host.json()["code"] == "invalid_host"

    bad_origin = client.post(
        "/api/session/start",
        headers={**_auth(security), "Origin": "http://evil.example"},
        json={"module": "git", "scenario": "merge-conflict"},
    )
    assert bad_origin.status_code == 403
