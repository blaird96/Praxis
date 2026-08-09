"""Active-session read, check, start, and reset endpoints."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Query, Request

from praxis import runner
from praxis.api.schemas import (
    AssignmentOut,
    CheckResultOut,
    ObjectiveOut,
    SessionOut,
    StartSessionRequest,
)
from praxis.models import Assignment, CheckResult, Session
from praxis.session import load_global_state
from praxis.terminal.registry import TerminalRegistry

router = APIRouter(prefix="/session", tags=["session"])


def _assignment_out(assignment: Assignment) -> AssignmentOut:
    return AssignmentOut(
        title=assignment.title,
        summary=assignment.summary,
        objectives=list(assignment.objectives),
    )


def _check_out(result: CheckResult) -> CheckResultOut:
    return CheckResultOut(
        passed=result.passed,
        objectives=[
            ObjectiveOut(
                id=item.id,
                description=item.description,
                passed=item.passed,
                detail=item.detail,
            )
            for item in result.objectives
        ],
    )


def _session_out(
    session: Session,
    assignment: Assignment,
    check: CheckResult | None = None,
    *,
    previous_session_id: str | None = None,
) -> SessionOut:
    return SessionOut(
        session_id=session.session_id,
        module=session.module,
        scenario=session.scenario,
        status=str(session.status),
        workspace_path=str(Path(session.workspace_path).resolve()),
        repo_path=str(Path(session.repo_path).resolve()),
        assignment=_assignment_out(assignment),
        check=_check_out(check) if check is not None else None,
        previous_session_id=previous_session_id,
    )


async def _close_terminals(request: Request, session_id: str | None) -> None:
    if not session_id:
        return
    registry: TerminalRegistry = request.app.state.terminal_registry
    await registry.close_for_session(session_id)


@router.get("", response_model=SessionOut)
def get_session(
    include_check: bool = Query(
        default=False,
        description="When true, run validation and include results.",
    ),
) -> SessionOut:
    session = runner.require_active_session()
    assignment = runner.active_assignment()
    check_result = None
    if include_check:
        check_result = runner.check_active().result
    return _session_out(session, assignment, check_result)


@router.post("/check", response_model=SessionOut)
def check_session() -> SessionOut:
    outcome = runner.check_active()
    assignment = runner.active_assignment()
    return _session_out(outcome.session, assignment, outcome.result)


@router.post("/start", response_model=SessionOut)
async def start_session(request: Request, body: StartSessionRequest) -> SessionOut:
    """Start a scenario via the existing transactional runner."""
    previous_id = load_global_state().active_session_id
    # Tear down shells for the session being replaced before switching.
    await _close_terminals(request, previous_id)
    started = runner.start(body.module, body.scenario)
    check_result = runner.check_active().result
    return _session_out(
        started.session,
        started.assignment,
        check_result,
        previous_session_id=started.previous_session_id,
    )


@router.post("/reset", response_model=SessionOut)
async def reset_session(request: Request) -> SessionOut:
    """Recreate the active exercise repository and re-run scenario setup."""
    active = runner.require_active_session()
    await _close_terminals(request, active.session_id)
    reset = runner.reset_active()
    check_result = runner.check_active().result
    return _session_out(reset.session, reset.assignment, check_result)
