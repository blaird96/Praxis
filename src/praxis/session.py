"""Session persistence, activation, and hybrid discovery."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from praxis.errors import SessionNotFoundError
from praxis.models import Session, SessionStatus
from praxis.paths import (
    ensure_praxis_home,
    praxis_home,
    repo_dir,
    scenario_state_file,
    session_file,
    state_path,
    workspace_path,
    workspaces_root,
)
from praxis.workspace import create_provisional_workspace, remove_workspace


class GlobalState(BaseModel):
    active_session_id: str | None = None


class ResolvedSession(BaseModel):
    session: Session
    source: str  # "cwd" | "active"
    is_active: bool = False


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, default=str) + "\n",
        encoding="utf-8",
    )


def load_global_state(home: Path | None = None) -> GlobalState:
    path = state_path(home)
    if not path.exists():
        return GlobalState()
    return GlobalState.model_validate(_read_json(path))


def save_global_state(state: GlobalState, home: Path | None = None) -> None:
    root = ensure_praxis_home(home)
    _write_json(state_path(root), state.model_dump(mode="json"))


def load_session(workspace: Path) -> Session:
    path = session_file(workspace)
    if not path.exists():
        raise SessionNotFoundError(f"No session metadata at {path}")
    return Session.model_validate(_read_json(path))


def save_session(session: Session) -> None:
    workspace = Path(session.workspace_path)
    _write_json(
        session_file(workspace),
        session.model_dump(mode="json"),
    )


def save_scenario_state(workspace: Path, state: dict[str, Any]) -> None:
    _write_json(scenario_state_file(workspace), state)


def load_scenario_state(workspace: Path) -> dict[str, Any] | None:
    path = scenario_state_file(workspace)
    if not path.exists():
        return None
    return _read_json(path)


def begin_session(
    *,
    module: str,
    scenario: str,
    session_id: str | None = None,
    home: Path | None = None,
) -> Session:
    """Create a provisional workspace and session record (not yet active)."""
    root = ensure_praxis_home(home)
    workspace = create_provisional_workspace(session_id, home=root)
    sid = workspace.name
    session = Session(
        session_id=sid,
        module=module,
        scenario=scenario,
        created_at=datetime.now(UTC),
        workspace_path=workspace,
        repo_path=repo_dir(workspace),
        status=SessionStatus.PROVISIONAL,
    )
    save_session(session)
    return session


def activate_session(
    session: Session,
    *,
    scenario_state: dict[str, Any] | None = None,
    home: Path | None = None,
) -> Session:
    """Persist finalized session metadata and set the global active pointer."""
    root = ensure_praxis_home(home)
    workspace = Path(session.workspace_path).resolve()

    if scenario_state is not None:
        save_scenario_state(workspace, scenario_state)
        session.scenario_state = scenario_state

    session.status = SessionStatus.ACTIVE
    session.workspace_path = workspace
    session.repo_path = repo_dir(workspace).resolve()
    save_session(session)

    state = load_global_state(root)
    state.active_session_id = session.session_id
    save_global_state(state, root)
    return session


def abandon_provisional_session(
    session: Session,
    *,
    home: Path | None = None,
) -> None:
    """Remove a failed provisional workspace; leave active pointer unchanged."""
    workspace = Path(session.workspace_path)
    remove_workspace(workspace, home=home)
    # Explicitly do not touch global state.


def _is_workspace_root(path: Path) -> bool:
    return session_file(path).is_file() and (path / "repo").exists()


def find_workspace_from_cwd(cwd: Path | None = None) -> Path | None:
    """Walk upward from cwd looking for a Praxis workspace root."""
    current = (cwd or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if _is_workspace_root(candidate):
            return candidate
    return None


def load_active_session(home: Path | None = None) -> Session | None:
    root = home or praxis_home()
    state = load_global_state(root)
    if not state.active_session_id:
        return None
    workspace = workspace_path(state.active_session_id, root)
    if not session_file(workspace).is_file():
        return None
    return load_session(workspace)


def resolve_session(
    *,
    cwd: Path | None = None,
    home: Path | None = None,
) -> ResolvedSession:
    """Hybrid discovery: cwd workspace first, else recorded active session."""
    root = home or praxis_home()
    active = load_global_state(root).active_session_id

    workspace = find_workspace_from_cwd(cwd)
    if workspace is not None:
        session = load_session(workspace)
        return ResolvedSession(
            session=session,
            source="cwd",
            is_active=session.session_id == active,
        )

    session = load_active_session(root)
    if session is not None:
        return ResolvedSession(
            session=session,
            source="active",
            is_active=True,
        )

    raise SessionNotFoundError(
        "No active Praxis session. Run "
        "`praxis start <module> --scenario <id>` or `cd` into a workspace."
    )


def list_workspace_ids(home: Path | None = None) -> list[str]:
    """Return retained session ids (workspace directory names)."""
    root = workspaces_root(home or praxis_home())
    if not root.exists():
        return []
    return sorted(
        path.name
        for path in root.iterdir()
        if path.is_dir() and _is_workspace_root(path)
    )
