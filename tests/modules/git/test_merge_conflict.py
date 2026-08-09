"""Tests for the git merge-conflict scenario."""

from __future__ import annotations

from pathlib import Path

import pytest

from praxis.errors import ProcessError
from praxis.modules.git import git_ops
from praxis.modules.git.scenarios.merge_conflict import (
    EXPECTED_RESOLVED_CONTENT,
    GREETING_FILE,
    MergeConflictScenario,
    MergeConflictState,
)
from praxis.process import run


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    path = tmp_path / "repo"
    path.mkdir()
    return path


@pytest.fixture
def scenario() -> MergeConflictScenario:
    return MergeConflictScenario()


def _write(repo_path: Path, content: str) -> None:
    (repo_path / GREETING_FILE).write_bytes(content.encode("utf-8"))


def _resolve_merge(repo_path: Path, content: str = EXPECTED_RESOLVED_CONTENT) -> None:
    _write(repo_path, content)
    git_ops.add_all(repo_path)
    git_ops.commit(repo_path, "Resolve merge conflict")


def test_setup_leaves_conflict_and_stable_shas(
    scenario: MergeConflictScenario, repo: Path
) -> None:
    state = scenario.setup(repo)

    assert isinstance(state, MergeConflictState)
    assert git_ops.current_branch(repo) == "main"
    assert git_ops.merge_head_exists(repo)
    assert git_ops.has_unmerged_paths(repo)
    text = (repo / GREETING_FILE).read_text(encoding="utf-8")
    assert "<<<<<<<" in text
    assert git_ops.rev_parse(repo, state.base_sha) == state.base_sha
    assert git_ops.rev_parse(repo, state.main_tip_sha) == state.main_tip_sha
    assert git_ops.rev_parse(repo, state.feature_tip_sha) == state.feature_tip_sha
    assert git_ops.rev_parse(repo, "HEAD") == state.main_tip_sha
    assert git_ops.rev_parse(repo, "MERGE_HEAD") == state.feature_tip_sha
    assert git_ops.rev_parse(repo, "feature") == state.feature_tip_sha


def test_state_round_trip_through_pydantic(
    scenario: MergeConflictScenario, repo: Path
) -> None:
    state = scenario.setup(repo)
    raw = state.model_dump(mode="json")
    restored = scenario.state_model.model_validate(raw)
    assert restored == state
    assert isinstance(restored, MergeConflictState)


def test_validate_objective_matrix_immediately_after_setup(
    scenario: MergeConflictScenario, repo: Path
) -> None:
    state = scenario.setup(repo)
    result = scenario.validate(repo, state)
    assert result.passed is False
    by_id = {item.id: item.passed for item in result.objectives}
    assert by_id == {
        "on-main": True,
        "no-unmerged": False,
        "merge-finished": False,
        "clean-tree": False,
        "merge-commit": False,
        "merge-parents": False,
        "greeting-content": False,
        "no-markers": False,
    }


def test_validate_fails_immediately_after_setup(
    scenario: MergeConflictScenario, repo: Path
) -> None:
    state = scenario.setup(repo)
    result = scenario.validate(repo, state)
    assert result.passed is False
    failed = {item.id for item in result.objectives if not item.passed}
    assert "no-unmerged" in failed
    assert "merge-finished" in failed
    assert "clean-tree" in failed
    assert "merge-commit" in failed
    assert "greeting-content" in failed
    assert "no-markers" in failed


def test_validate_passes_after_correct_merge(
    scenario: MergeConflictScenario, repo: Path
) -> None:
    state = scenario.setup(repo)
    _resolve_merge(repo)
    result = scenario.validate(repo, state)
    assert result.passed is True
    assert all(item.passed for item in result.objectives)
    parents = git_ops.commit_parents(repo, "HEAD")
    assert parents == [state.main_tip_sha, state.feature_tip_sha]


def test_validate_fails_when_index_unresolved(
    scenario: MergeConflictScenario, repo: Path
) -> None:
    state = scenario.setup(repo)
    _write(repo, EXPECTED_RESOLVED_CONTENT)
    # Do not add/commit — conflict remains in the index.
    result = scenario.validate(repo, state)
    assert result.passed is False
    by_id = {item.id: item for item in result.objectives}
    assert by_id["no-unmerged"].passed is False
    assert by_id["merge-finished"].passed is False
    assert by_id["greeting-content"].passed is True
    # Even with markers removed from the working tree, unmerged index stages
    # mean the conflict is not resolved for this objective.
    assert by_id["no-markers"].passed is False


def test_validate_fails_for_abort_and_single_parent_commit(
    scenario: MergeConflictScenario, repo: Path
) -> None:
    state = scenario.setup(repo)
    run(["git", "merge", "--abort"], cwd=repo)
    assert not git_ops.merge_head_exists(repo)

    _write(repo, EXPECTED_RESOLVED_CONTENT)
    git_ops.add_all(repo)
    git_ops.commit(repo, "Manual recreation without merge")

    result = scenario.validate(repo, state)
    assert result.passed is False
    by_id = {item.id: item for item in result.objectives}
    assert by_id["greeting-content"].passed is True
    assert by_id["merge-commit"].passed is False
    assert by_id["merge-parents"].passed is False


def test_validate_fails_for_wrong_content(
    scenario: MergeConflictScenario, repo: Path
) -> None:
    state = scenario.setup(repo)
    _resolve_merge(repo, "wrong content\n")
    result = scenario.validate(repo, state)
    assert result.passed is False
    by_id = {item.id: item for item in result.objectives}
    assert by_id["greeting-content"].passed is False
    assert by_id["merge-commit"].passed is True
    assert by_id["merge-parents"].passed is True


def test_validate_fails_for_detached_head(
    scenario: MergeConflictScenario, repo: Path
) -> None:
    state = scenario.setup(repo)
    _resolve_merge(repo)
    head = git_ops.rev_parse(repo, "HEAD")
    git_ops.checkout(repo, head)

    result = scenario.validate(repo, state)
    assert result.passed is False
    by_id = {item.id: item for item in result.objectives}
    assert by_id["on-main"].passed is False
    assert by_id["merge-commit"].passed is True
    assert by_id["merge-parents"].passed is True


def test_validate_fails_for_wrong_merge_parents(
    scenario: MergeConflictScenario, repo: Path
) -> None:
    state = scenario.setup(repo)
    run(["git", "merge", "--abort"], cwd=repo)

    _write(repo, "extra commit on main\nShared line\n")
    git_ops.add_all(repo)
    git_ops.commit(repo, "Diverging main further")

    result = git_ops.merge(repo, "feature", allowed_returncodes={0, 1})
    assert result.returncode == 1
    _resolve_merge(repo)

    check = scenario.validate(repo, state)
    assert check.passed is False
    by_id = {item.id: item for item in check.objectives}
    assert by_id["merge-commit"].passed is True
    assert by_id["merge-parents"].passed is False
    assert by_id["greeting-content"].passed is True


def test_validate_passes_after_feature_ref_deleted(
    scenario: MergeConflictScenario, repo: Path
) -> None:
    state = scenario.setup(repo)
    _resolve_merge(repo)
    run(["git", "branch", "-D", "feature"], cwd=repo)

    with pytest.raises(ProcessError):
        git_ops.rev_parse(repo, "feature")

    result = scenario.validate(repo, state)
    assert result.passed is True
    assert all(item.passed for item in result.objectives)
