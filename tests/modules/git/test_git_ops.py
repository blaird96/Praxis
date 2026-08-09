"""Tests for thin git_ops helpers (temporary repos only)."""

from __future__ import annotations

from pathlib import Path

import pytest

from praxis.errors import ProcessError
from praxis.modules.git import git_ops
from praxis.process import run


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    path = tmp_path / "repo"
    path.mkdir()
    return path


@pytest.fixture
def hooks(tmp_path: Path) -> Path:
    path = tmp_path / "hooks"
    path.mkdir()
    return path


def _write(repo_path: Path, relative: str, content: str) -> None:
    target = repo_path / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    # newline="" avoids platform translation interfering with autocrlf tests
    target.write_bytes(content.encode("utf-8"))


def test_init_creates_main_branch(repo: Path) -> None:
    git_ops.init(repo)
    assert (repo / ".git").is_dir()
    assert git_ops.current_branch(repo) == "main"


def test_configure_lab_repo_is_local_only(repo: Path, hooks: Path) -> None:
    git_ops.init(repo)

    before_global_name = run(
        ["git", "config", "--global", "--get", "user.name"],
        allowed_returncodes={0, 1},
    )
    before_global_email = run(
        ["git", "config", "--global", "--get", "user.email"],
        allowed_returncodes={0, 1},
    )

    git_ops.configure_lab_repo(
        repo,
        hooks_path=hooks,
        user_name="Praxis Local Only",
        user_email="local-only@example.invalid",
    )

    assert git_ops.get_local_config(repo, "user.name") == "Praxis Local Only"
    assert git_ops.get_local_config(repo, "user.email") == "local-only@example.invalid"
    assert git_ops.get_local_config(repo, "commit.gpgSign") == "false"
    assert git_ops.get_local_config(repo, "core.autocrlf") == "false"
    assert Path(git_ops.get_local_config(repo, "core.hooksPath")) == hooks.resolve()

    after_global_name = run(
        ["git", "config", "--global", "--get", "user.name"],
        allowed_returncodes={0, 1},
    )
    after_global_email = run(
        ["git", "config", "--global", "--get", "user.email"],
        allowed_returncodes={0, 1},
    )
    assert after_global_name.returncode == before_global_name.returncode
    assert after_global_name.stdout == before_global_name.stdout
    assert after_global_email.returncode == before_global_email.returncode
    assert after_global_email.stdout == before_global_email.stdout
    assert "Praxis Local Only" not in after_global_name.stdout
    assert "local-only@example.invalid" not in after_global_email.stdout


def test_commit_and_branch_operations(repo: Path, hooks: Path) -> None:
    git_ops.init(repo)
    git_ops.configure_lab_repo(repo, hooks_path=hooks)

    _write(repo, "greeting.txt", "base\n")
    git_ops.add_all(repo)
    base_sha = git_ops.commit(repo, "base")
    assert len(base_sha) == 40
    assert git_ops.rev_parse(repo, "HEAD") == base_sha
    assert git_ops.commit_parents(repo, "HEAD") == []
    assert git_ops.is_clean(repo)

    git_ops.create_branch(repo, "feature")
    git_ops.switch_branch(repo, "feature")
    assert git_ops.current_branch(repo) == "feature"

    _write(repo, "greeting.txt", "feature\n")
    git_ops.add_all(repo)
    feature_sha = git_ops.commit(repo, "feature change")
    assert git_ops.commit_parents(repo, "HEAD") == [base_sha]

    git_ops.checkout(repo, "main")
    assert git_ops.current_branch(repo) == "main"
    assert git_ops.rev_parse(repo, "feature") == feature_sha


def test_merge_conflict_allowed_returncode(repo: Path, hooks: Path) -> None:
    git_ops.init(repo)
    git_ops.configure_lab_repo(repo, hooks_path=hooks)

    _write(repo, "greeting.txt", "base\n")
    git_ops.add_all(repo)
    git_ops.commit(repo, "base")

    git_ops.create_branch(repo, "feature")

    _write(repo, "greeting.txt", "main side\n")
    git_ops.add_all(repo)
    main_tip = git_ops.commit(repo, "main change")

    git_ops.checkout(repo, "feature")
    _write(repo, "greeting.txt", "feature side\n")
    git_ops.add_all(repo)
    feature_tip = git_ops.commit(repo, "feature change")

    git_ops.checkout(repo, "main")

    with pytest.raises(ProcessError) as exc_info:
        git_ops.merge(repo, "feature")
    assert exc_info.value.returncode == 1
    # Default allowed_returncodes={0} leaves the conflicted merge in place.
    assert git_ops.has_unmerged_paths(repo)
    assert git_ops.merge_head_exists(repo)
    assert git_ops.unmerged_entries(repo)
    assert "greeting.txt" in git_ops.status_porcelain(repo)
    assert git_ops.rev_parse(repo, "HEAD") == main_tip
    assert git_ops.rev_parse(repo, "feature") == feature_tip

    # Explicitly allowing 1 makes conflict a non-raising outcome for setup.
    # Abort and recreate is unnecessary: MERGE_HEAD already present; instead
    # verify allowed_returncodes accepts the conflict exit on a fresh clone-like redo.
    run(["git", "merge", "--abort"], cwd=repo)
    result = git_ops.merge(repo, "feature", allowed_returncodes={0, 1})
    assert result.returncode == 1
    assert git_ops.has_unmerged_paths(repo)


def test_sha_and_parent_helpers_after_successful_merge(repo: Path, hooks: Path) -> None:
    git_ops.init(repo)
    git_ops.configure_lab_repo(repo, hooks_path=hooks)

    _write(repo, "a.txt", "one\n")
    git_ops.add_all(repo)
    git_ops.commit(repo, "base")

    git_ops.switch_branch(repo, "feature", create=True)
    _write(repo, "b.txt", "two\n")
    git_ops.add_all(repo)
    feature_tip = git_ops.commit(repo, "feature")

    git_ops.checkout(repo, "main")
    _write(repo, "c.txt", "three\n")
    git_ops.add_all(repo)
    main_tip = git_ops.commit(repo, "main")

    result = git_ops.merge(
        repo,
        "feature",
        no_edit=True,
        allowed_returncodes={0},
    )
    assert result.returncode == 0
    assert not git_ops.merge_head_exists(repo)
    assert not git_ops.has_unmerged_paths(repo)
    assert git_ops.is_clean(repo)

    parents = git_ops.commit_parents(repo, "HEAD")
    assert parents == [main_tip, feature_tip]


def test_detached_head_detection(repo: Path, hooks: Path) -> None:
    git_ops.init(repo)
    git_ops.configure_lab_repo(repo, hooks_path=hooks)
    _write(repo, "f.txt", "x\n")
    git_ops.add_all(repo)
    sha = git_ops.commit(repo, "c")

    assert git_ops.is_detached_head(repo) is False
    git_ops.checkout(repo, sha)
    assert git_ops.is_detached_head(repo) is True
