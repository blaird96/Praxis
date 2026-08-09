"""Tests for configsvc helpers and extended git_ops."""

from __future__ import annotations

from pathlib import Path

from praxis.modules.git import git_ops
from praxis.modules.git.configsvc import init_configsvc_repo, seed_configsvc_files


def test_init_configsvc_repo(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    (workspace / ".praxis" / "hooks").mkdir(parents=True)
    repo = workspace / "repo"
    repo.mkdir()
    sha = init_configsvc_repo(repo)
    assert len(sha) == 40
    assert git_ops.is_clean(repo)
    assert (repo / "app.py").is_file()


def test_seed_files_only(tmp_path: Path) -> None:
    seed_configsvc_files(tmp_path)
    assert (tmp_path / "settings.toml").is_file()
