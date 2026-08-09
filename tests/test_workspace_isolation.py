"""Tests for workspace layout, isolation, and path safety."""

from __future__ import annotations

from pathlib import Path

import pytest

from praxis.errors import WorkspaceError
from praxis.paths import hooks_dir, praxis_meta_dir, repo_dir, session_file
from praxis.session import begin_session
from praxis.workspace import (
    assert_safe_repo_path,
    create_provisional_workspace,
    remove_workspace,
    reset_repo,
)


def test_provisional_layout(praxis_home: Path) -> None:
    workspace = create_provisional_workspace(home=praxis_home)
    assert praxis_meta_dir(workspace).is_dir()
    assert hooks_dir(workspace).is_dir()
    assert repo_dir(workspace).is_dir()
    assert not (repo_dir(workspace) / ".praxis").exists()
    assert list(repo_dir(workspace).iterdir()) == []


def test_metadata_not_inside_repo(praxis_home: Path) -> None:
    session = begin_session(module="git", scenario="merge-conflict", home=praxis_home)
    repo = Path(session.repo_path)
    meta = Path(session.workspace_path) / ".praxis"

    assert session_file(session.workspace_path).is_file()
    assert meta.is_dir()
    assert meta.resolve().parent == Path(session.workspace_path).resolve()
    assert not (repo / ".praxis").exists()
    assert not any(repo.rglob(".praxis"))


def test_reset_repo_recreates_empty_directory(praxis_home: Path) -> None:
    workspace = create_provisional_workspace(home=praxis_home)
    repo = repo_dir(workspace)
    (repo / "dirty.txt").write_text("x", encoding="utf-8")
    (repo / "nested").mkdir()
    (repo / "nested" / "y.txt").write_text("y", encoding="utf-8")

    reset_repo(workspace)
    assert repo.is_dir()
    assert list(repo.iterdir()) == []


def test_reset_repo_succeeds_when_cwd_is_inside_repo(
    praxis_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Windows cannot rmtree a directory that is the process cwd."""
    workspace = create_provisional_workspace(home=praxis_home)
    repo = repo_dir(workspace)
    (repo / "dirty.txt").write_text("x", encoding="utf-8")
    monkeypatch.chdir(repo)

    reset_repo(workspace)

    assert repo.is_dir()
    assert list(repo.iterdir()) == []
    assert not Path.cwd().resolve().is_relative_to(repo.resolve())


def test_reset_refuses_symlink_repo(praxis_home: Path, tmp_path: Path) -> None:
    workspace = create_provisional_workspace(home=praxis_home)
    repo = repo_dir(workspace)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("nope", encoding="utf-8")

    repo.rmdir()
    try:
        repo.symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"symlinks unavailable: {exc}")

    with pytest.raises(WorkspaceError, match="symlink"):
        reset_repo(workspace)

    assert (outside / "secret.txt").read_text(encoding="utf-8") == "nope"


def test_assert_safe_repo_path_rejects_escape(
    praxis_home: Path, tmp_path: Path
) -> None:
    workspace = create_provisional_workspace(home=praxis_home)
    outsider = tmp_path / "escape"
    outsider.mkdir()
    with pytest.raises(WorkspaceError, match="not the workspace repo"):
        assert_safe_repo_path(workspace, outsider)


def test_remove_workspace_refuses_outside_root(
    praxis_home: Path, tmp_path: Path
) -> None:
    outsider = tmp_path / "not-a-workspace"
    outsider.mkdir()
    with pytest.raises(WorkspaceError, match="outside workspaces root"):
        remove_workspace(outsider, home=praxis_home)


def test_remove_workspace_refuses_workspaces_root(praxis_home: Path) -> None:
    from praxis.paths import workspaces_root

    root = workspaces_root(praxis_home)
    root.mkdir(parents=True, exist_ok=True)
    with pytest.raises(WorkspaceError, match="workspaces root"):
        remove_workspace(root, home=praxis_home)
