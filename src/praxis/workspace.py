"""Create and reset disposable training workspaces."""

from __future__ import annotations

import os
import shutil
import stat
import uuid
from pathlib import Path

from praxis.errors import WorkspaceError
from praxis.paths import (
    ensure_praxis_home,
    hooks_dir,
    praxis_meta_dir,
    repo_dir,
    workspace_path,
    workspaces_root,
)


def new_session_id() -> str:
    return uuid.uuid4().hex[:12]


def create_provisional_workspace(
    session_id: str | None = None,
    *,
    home: Path | None = None,
) -> Path:
    """Create a provisional workspace layout; does not touch active state.

    Layout::

        workspaces/<id>/
          .praxis/
            hooks/
          repo/
    """
    root = ensure_praxis_home(home)
    sid = session_id or new_session_id()
    workspace = workspace_path(sid, root)

    if workspace.exists():
        raise WorkspaceError(f"Workspace already exists: {workspace}")

    praxis_meta_dir(workspace).mkdir(parents=True, exist_ok=False)
    hooks_dir(workspace).mkdir(parents=True, exist_ok=False)
    repo_dir(workspace).mkdir(parents=True, exist_ok=False)
    return workspace.resolve()


def expected_repo_path(workspace: Path) -> Path:
    return (workspace / "repo").resolve()


def assert_safe_repo_path(workspace: Path, repo_path: Path) -> Path:
    """Refuse destructive ops if repo path escapes workspace or is a symlink.

    Uses pathlib relationships (``is_relative_to``), not string prefixes.
    """
    workspace_resolved = workspace.resolve()
    expected = expected_repo_path(workspace_resolved)
    declared = Path(repo_path)

    # Refuse if the expected repo location has been replaced by a symlink.
    repo_link = workspace_resolved / "repo"
    if repo_link.is_symlink():
        raise WorkspaceError(f"Refusing unsafe repo path: {repo_link} is a symlink")

    if declared.is_symlink():
        raise WorkspaceError(f"Refusing unsafe repo path: {declared} is a symlink")

    try:
        resolved = declared.resolve()
    except OSError as exc:
        raise WorkspaceError(f"Cannot resolve repo path: {declared}") from exc

    if resolved != expected:
        raise WorkspaceError(
            f"Repo path {resolved} is not the workspace repo directory {expected}"
        )

    if not resolved.is_relative_to(workspace_resolved):
        raise WorkspaceError(
            f"Repo path {resolved} escapes workspace {workspace_resolved}"
        )

    return resolved


def _rmtree(path: Path) -> None:
    """Remove a directory tree, clearing read-only bits (common on Windows/.git)."""

    def _onexc(func: object, path_str: str, exc: BaseException) -> None:
        try:
            os.chmod(path_str, stat.S_IWRITE)
            if callable(func):
                func(path_str)
        except OSError as retry_exc:
            raise exc from retry_exc

    shutil.rmtree(path, onexc=_onexc)


def reset_repo(workspace: Path, repo_path: Path | None = None) -> Path:
    """Delete and recreate the exercise repo directory after safety checks."""
    workspace_resolved = workspace.resolve()
    target = assert_safe_repo_path(
        workspace_resolved,
        repo_path if repo_path is not None else repo_dir(workspace_resolved),
    )

    if target.exists():
        _rmtree(target)

    target.mkdir(parents=True, exist_ok=False)
    return target


def remove_workspace(workspace: Path, *, home: Path | None = None) -> None:
    """Remove a provisional workspace directory after failed setup."""
    workspace_resolved = workspace.resolve()
    workspaces = workspaces_root(home).resolve()

    if not workspace_resolved.is_relative_to(workspaces):
        raise WorkspaceError(
            f"Refusing to remove path outside workspaces root: {workspace_resolved}"
        )

    if workspace_resolved == workspaces:
        raise WorkspaceError("Refusing to remove workspaces root")

    if workspace_resolved.parent != workspaces:
        raise WorkspaceError(
            f"Refusing to remove nested path {workspace_resolved}; "
            f"expected a direct child of {workspaces}"
        )

    if workspace_resolved.exists():
        _rmtree(workspace_resolved)
