"""Create and reset disposable training workspaces."""

from __future__ import annotations

import os
import shutil
import stat
import time
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

_RMTREE_ATTEMPTS = 6
_RMTREE_RETRY_SECONDS = 0.05


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


def ensure_cwd_outside(path: Path) -> Path | None:
    """If the process cwd is inside ``path``, move it to a safe parent.

    Windows cannot delete a directory that is the current working directory of
    the running process (common when ``praxis ui`` is launched from the
    exercise repo). Returns the previous cwd when a change was made.
    """
    target = path.resolve()
    try:
        cwd = Path.cwd().resolve()
    except OSError:
        return None

    if cwd != target and not cwd.is_relative_to(target):
        return None

    safe = target.parent if target.parent.exists() else Path.home()
    if safe.resolve() == cwd or safe.resolve().is_relative_to(target):
        safe = Path.home()
    os.chdir(safe)
    return cwd


def _rmtree(path: Path) -> None:
    """Remove a directory tree, clearing read-only bits (common on Windows/.git)."""
    target = path.resolve()
    ensure_cwd_outside(target)

    def _onexc(func: object, path_str: str, exc: BaseException) -> None:
        try:
            os.chmod(path_str, stat.S_IWRITE)
            if callable(func):
                func(path_str)
        except OSError as retry_exc:
            raise exc from retry_exc

    last_error: OSError | None = None
    for attempt in range(_RMTREE_ATTEMPTS):
        ensure_cwd_outside(target)
        try:
            if not target.exists():
                return
            shutil.rmtree(target, onexc=_onexc)
            return
        except OSError as exc:
            last_error = exc
            time.sleep(_RMTREE_RETRY_SECONDS * (attempt + 1))

    detail = str(last_error) if last_error else "unknown error"
    raise WorkspaceError(
        f"Could not remove {target}: {detail}. "
        "Close any shells or programs using that directory (including a "
        "terminal whose cwd is inside the exercise repo), then try again."
    ) from last_error


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
