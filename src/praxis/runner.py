"""Orchestration for start / check / reset / status."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from praxis.errors import ScenarioStateError, SessionNotFoundError
from praxis.models import Assignment, CheckResult, Session
from praxis.progress import record_check_result
from praxis.registry import bootstrap_registry, get_scenario
from praxis.session import (
    ResolvedSession,
    abandon_provisional_session,
    activate_session,
    begin_session,
    load_active_session,
    load_global_state,
    load_scenario_state,
    persist_session_outcome,
    resolve_session,
)
from praxis.workspace import reset_repo


@dataclass(frozen=True, slots=True)
class StartResult:
    session: Session
    assignment: Assignment
    repo_path: Path
    previous_session_id: str | None = None


@dataclass(frozen=True, slots=True)
class CheckOutcome:
    result: CheckResult
    session: Session


@dataclass(frozen=True, slots=True)
class ResetResult:
    session: Session
    assignment: Assignment
    repo_path: Path


@dataclass(frozen=True, slots=True)
class StatusResult:
    resolved: ResolvedSession


def _load_typed_state(session: Session, scenario: Any) -> Any:
    workspace = Path(session.workspace_path)
    raw = load_scenario_state(workspace)
    if raw is None:
        state_path = workspace / ".praxis" / "scenario_state.json"
        raise ScenarioStateError(
            f"Missing scenario state at {state_path}. "
            "Try `praxis reset` or start a new session."
        )
    try:
        return scenario.state_model.model_validate(raw)
    except ValidationError as exc:
        raise ScenarioStateError(
            "Persisted scenario state is invalid and cannot be loaded. "
            "Try `praxis reset` or start a new session."
        ) from exc


def start(
    module_id: str,
    scenario_id: str,
    *,
    home: Path | None = None,
) -> StartResult:
    """Create a disposable workspace, run setup, then activate the session."""
    bootstrap_registry()
    scenario = get_scenario(module_id, scenario_id)
    previous_session_id = load_global_state(home).active_session_id

    session = begin_session(
        module=module_id,
        scenario=scenario_id,
        home=home,
    )
    try:
        state = scenario.setup(Path(session.repo_path))
        state_data = state.model_dump(mode="json")
        session = activate_session(
            session,
            scenario_state=state_data,
            home=home,
        )
    except Exception:
        abandon_provisional_session(session, home=home)
        raise

    retained = (
        previous_session_id
        if previous_session_id and previous_session_id != session.session_id
        else None
    )
    return StartResult(
        session=session,
        assignment=scenario.assignment(),
        repo_path=Path(session.repo_path),
        previous_session_id=retained,
    )


def check(
    *,
    cwd: Path | None = None,
    home: Path | None = None,
) -> CheckOutcome:
    """Validate using hybrid session discovery (CLI)."""
    bootstrap_registry()
    resolved = resolve_session(cwd=cwd, home=home)
    return _validate_session(resolved.session, home=home)


def check_active(*, home: Path | None = None) -> CheckOutcome:
    """Validate the globally active session (web/app; ignores process cwd)."""
    bootstrap_registry()
    session = require_active_session(home=home)
    return _validate_session(session, home=home)


def require_active_session(*, home: Path | None = None) -> Session:
    """Return the active session or raise ``SessionNotFoundError``."""
    session = load_active_session(home)
    if session is None:
        raise SessionNotFoundError(
            "No active Praxis session. Start one with "
            "`praxis start <module> --scenario <id>` or the Praxis app."
        )
    return session


def active_assignment(*, home: Path | None = None) -> Assignment:
    """Assignment for the active session's scenario."""
    bootstrap_registry()
    session = require_active_session(home=home)
    scenario = get_scenario(session.module, session.scenario)
    return scenario.assignment()


def _validate_session(session: Session, *, home: Path | None = None) -> CheckOutcome:
    scenario = get_scenario(session.module, session.scenario)
    state = _load_typed_state(session, scenario)
    result = scenario.validate(Path(session.repo_path), state)
    record_check_result(session.module, session.scenario, result.passed, home=home)
    return CheckOutcome(result=result, session=session)


def reset(
    *,
    cwd: Path | None = None,
    home: Path | None = None,
) -> ResetResult:
    """Recreate the exercise repo and re-run setup; do not change active pointer."""
    bootstrap_registry()
    resolved = resolve_session(cwd=cwd, home=home)
    return _reset_session(resolved.session)


def reset_active(*, home: Path | None = None) -> ResetResult:
    """Reset the globally active session (web/app; ignores process cwd)."""
    bootstrap_registry()
    session = require_active_session(home=home)
    return _reset_session(session)


def _reset_session(session: Session) -> ResetResult:
    scenario = get_scenario(session.module, session.scenario)
    workspace = Path(session.workspace_path)
    repo_path = reset_repo(workspace, Path(session.repo_path))
    state = scenario.setup(repo_path)
    state_data = state.model_dump(mode="json")
    session = persist_session_outcome(session, scenario_state=state_data)
    return ResetResult(
        session=session,
        assignment=scenario.assignment(),
        repo_path=Path(session.repo_path),
    )


def status(
    *,
    cwd: Path | None = None,
    home: Path | None = None,
) -> StatusResult:
    bootstrap_registry()
    resolved = resolve_session(cwd=cwd, home=home)
    return StatusResult(resolved=resolved)
