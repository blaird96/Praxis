"""PRAXIS_HOME roots and workspace path helpers."""

from __future__ import annotations

import os
from pathlib import Path

PRAXIS_HOME_ENV = "PRAXIS_HOME"
DEFAULT_PRAXIS_HOME = Path.home() / ".praxis"


def praxis_home() -> Path:
    """Return the Praxis data root, honoring PRAXIS_HOME when set."""
    override = os.environ.get(PRAXIS_HOME_ENV)
    if override:
        return Path(override).expanduser().resolve()
    return DEFAULT_PRAXIS_HOME.resolve()


def state_path(home: Path | None = None) -> Path:
    return (home or praxis_home()) / "state.json"


def progress_path(home: Path | None = None) -> Path:
    return (home or praxis_home()) / "progress.json"


def coaching_prefs_path(home: Path | None = None) -> Path:
    return (home or praxis_home()) / "coaching_prefs.json"


def workspaces_root(home: Path | None = None) -> Path:
    return (home or praxis_home()) / "workspaces"


def workspace_path(session_id: str, home: Path | None = None) -> Path:
    return workspaces_root(home) / session_id


def praxis_meta_dir(workspace: Path) -> Path:
    return workspace / ".praxis"


def session_file(workspace: Path) -> Path:
    return praxis_meta_dir(workspace) / "session.json"


def scenario_state_file(workspace: Path) -> Path:
    return praxis_meta_dir(workspace) / "scenario_state.json"


def hooks_dir(workspace: Path) -> Path:
    return praxis_meta_dir(workspace) / "hooks"


def repo_dir(workspace: Path) -> Path:
    return workspace / "repo"


def ensure_praxis_home(home: Path | None = None) -> Path:
    """Create PRAXIS_HOME and workspaces root if missing; return home."""
    root = home or praxis_home()
    workspaces_root(root).mkdir(parents=True, exist_ok=True)
    return root
