"""CLI / runner end-to-end tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from praxis.cli import app
from praxis.errors import ScenarioSetupError
from praxis.modules.git import git_ops
from praxis.modules.git.scenarios.merge_conflict import (
    EXPECTED_RESOLVED_CONTENT,
    GREETING_FILE,
    MergeConflictScenario,
)
from praxis.paths import scenario_state_file, session_file
from praxis.registry import bootstrap_registry, clear_registry, get_scenario
from praxis.session import load_global_state, load_scenario_state, load_session

cli = CliRunner()


@pytest.fixture(autouse=True)
def _registry(praxis_home: Path) -> None:
    clear_registry()
    bootstrap_registry()
    yield
    clear_registry()


def _invoke(args: list[str], *, praxis_home: Path) -> object:
    return cli.invoke(app, args, env={"PRAXIS_HOME": str(praxis_home)})


def _start(praxis_home: Path) -> tuple[object, Path, Path]:
    result = _invoke(
        ["start", "git", "--scenario", "merge-conflict"],
        praxis_home=praxis_home,
    )
    assert result.exit_code == 0, result.output
    state = load_global_state(praxis_home)
    assert state.active_session_id
    session = load_session(praxis_home / "workspaces" / state.active_session_id)
    return result, Path(session.workspace_path), Path(session.repo_path)


def _resolve(repo: Path) -> None:
    (repo / GREETING_FILE).write_bytes(EXPECTED_RESOLVED_CONTENT.encode("utf-8"))
    git_ops.add_all(repo)
    git_ops.commit(repo, "Resolve merge conflict")


def test_bootstrap_registry_idempotent() -> None:
    clear_registry()
    bootstrap_registry()
    bootstrap_registry()
    scenario = get_scenario("git", "merge-conflict")
    assert scenario.id == "merge-conflict"


def test_start_creates_conflicted_exercise(praxis_home: Path) -> None:
    result, workspace, repo = _start(praxis_home)
    assert "Resolve a merge conflict" in result.output
    assert workspace.name in result.output
    assert "Exercise repository:" in result.output
    assert "cd " in result.output
    assert git_ops.merge_head_exists(repo)
    assert git_ops.has_unmerged_paths(repo)
    assert session_file(workspace).is_file()
    raw = load_scenario_state(workspace)
    assert raw is not None
    state = MergeConflictScenario.state_model.model_validate(raw)
    assert state.main_tip_sha
    assert state.feature_tip_sha
    assert load_global_state(praxis_home).active_session_id == workspace.name


def test_start_setup_failure_preserves_active(
    praxis_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _start(praxis_home)
    previous = load_global_state(praxis_home).active_session_id
    assert previous is not None
    before_workspaces = {
        p.name for p in (praxis_home / "workspaces").iterdir() if p.is_dir()
    }

    def _boom(self: MergeConflictScenario, repo_path: Path) -> object:
        raise ScenarioSetupError("forced setup failure")

    monkeypatch.setattr(MergeConflictScenario, "setup", _boom)
    clear_registry()
    bootstrap_registry()

    result = _invoke(
        ["start", "git", "--scenario", "merge-conflict"],
        praxis_home=praxis_home,
    )
    assert result.exit_code == 2
    assert "forced setup failure" in result.output
    assert "Traceback" not in result.output
    assert load_global_state(praxis_home).active_session_id == previous

    after_workspaces = {
        p.name for p in (praxis_home / "workspaces").iterdir() if p.is_dir()
    }
    assert after_workspaces == before_workspaces


def test_check_exit_codes(praxis_home: Path) -> None:
    _, _workspace, repo = _start(praxis_home)

    failed = _invoke(["check"], praxis_home=praxis_home)
    assert failed.exit_code == 1
    assert "FAIL" in failed.output

    _resolve(repo)
    passed = _invoke(["check"], praxis_home=praxis_home)
    assert passed.exit_code == 0
    assert "PASS" in passed.output
    assert "All objectives satisfied" in passed.output

    reset = _invoke(["reset"], praxis_home=praxis_home)
    assert reset.exit_code == 0, reset.output
    (repo / GREETING_FILE).write_bytes(b"nope\n")
    git_ops.add_all(repo)
    git_ops.commit(repo, "Wrong resolution")
    wrong = _invoke(["check"], praxis_home=praxis_home)
    assert wrong.exit_code == 1


def test_invalid_scenario_state_exit_2(praxis_home: Path) -> None:
    _, workspace, _repo = _start(praxis_home)
    scenario_state_file(workspace).write_text("{not-json", encoding="utf-8")
    result = _invoke(["check"], praxis_home=praxis_home)
    assert result.exit_code == 2
    assert "Error:" in result.output
    assert "Traceback" not in result.output


def test_reset_restores_conflict_and_fresh_state(praxis_home: Path) -> None:
    _, workspace, repo = _start(praxis_home)
    before = MergeConflictScenario.state_model.model_validate(
        load_scenario_state(workspace)
    )
    _resolve(repo)
    assert _invoke(["check"], praxis_home=praxis_home).exit_code == 0

    result = _invoke(["reset"], praxis_home=praxis_home)
    assert result.exit_code == 0, result.output
    assert "Reset" in result.output
    assert git_ops.merge_head_exists(repo)
    assert git_ops.has_unmerged_paths(repo)
    after = MergeConflictScenario.state_model.model_validate(
        load_scenario_state(workspace)
    )
    assert after.main_tip_sha != before.main_tip_sha
    assert after.feature_tip_sha != before.feature_tip_sha


def test_status_hybrid_discovery(
    praxis_home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _start(praxis_home)
    first_id = load_global_state(praxis_home).active_session_id
    assert first_id
    first_repo = praxis_home / "workspaces" / first_id / "repo"

    second = _invoke(
        ["start", "git", "--scenario", "merge-conflict"],
        praxis_home=praxis_home,
    )
    assert second.exit_code == 0
    assert f"Previous session {first_id} retained." in second.output
    second_id = load_global_state(praxis_home).active_session_id
    assert second_id != first_id

    monkeypatch.chdir(first_repo)
    local = _invoke(["status"], praxis_home=praxis_home)
    assert local.exit_code == 0, local.output
    assert first_id in local.output
    assert "Active" in local.output
    assert "no" in local.output
    assert "cwd" in local.output

    elsewhere = tmp_path / "outside"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    active = _invoke(["status"], praxis_home=praxis_home)
    assert active.exit_code == 0, active.output
    assert second_id in active.output
    assert "yes" in active.output
    assert "active" in active.output


def test_unknown_module_and_no_session_errors(
    praxis_home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    unknown = _invoke(
        ["start", "docker", "--scenario", "basic"],
        praxis_home=praxis_home,
    )
    assert unknown.exit_code == 2
    assert "Unknown module" in unknown.output
    assert "Traceback" not in unknown.output

    unknown_scenario = _invoke(
        ["start", "git", "--scenario", "rebase"],
        praxis_home=praxis_home,
    )
    assert unknown_scenario.exit_code == 2
    assert "Unknown scenario" in unknown_scenario.output
    assert "Traceback" not in unknown_scenario.output

    elsewhere = tmp_path / "empty"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    for command in ("check", "reset", "status"):
        result = _invoke([command], praxis_home=praxis_home)
        assert result.exit_code == 2, result.output
        assert "No active Praxis session" in result.output
        assert "Traceback" not in result.output


def test_invalid_state_model_fields_exit_2(praxis_home: Path) -> None:
    _, workspace, _repo = _start(praxis_home)
    scenario_state_file(workspace).write_text(
        json.dumps({"base_sha": "x"}),
        encoding="utf-8",
    )
    result = _invoke(["check"], praxis_home=praxis_home)
    assert result.exit_code == 2
    assert "Error:" in result.output
    assert "Traceback" not in result.output
