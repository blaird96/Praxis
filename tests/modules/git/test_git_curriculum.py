"""Tests for new Git curriculum scenarios (waves 1–4)."""

from __future__ import annotations

from pathlib import Path

import pytest

from praxis.modules.git import git_ops
from praxis.modules.git.configsvc import APP_PY, README_MD, SETTINGS_TOML, write_text
from praxis.modules.git.scenarios.bisect_regression import (
    ANSWER_FILE,
    BisectRegressionScenario,
)
from praxis.modules.git.scenarios.cherry_pick_hotfix import (
    HOTFIX_BRANCH,
    CherryPickHotfixScenario,
)
from praxis.modules.git.scenarios.clean_merge import (
    FEATURE_BRANCH as CLEAN_FEATURE,
)
from praxis.modules.git.scenarios.clean_merge import CleanMergeScenario
from praxis.modules.git.scenarios.discard_local import (
    KEEP_README,
    DiscardLocalScenario,
)
from praxis.modules.git.scenarios.diverged_remote import DivergedRemoteScenario
from praxis.modules.git.scenarios.feature_branch import (
    EXPECTED_README,
    EXPECTED_SETTINGS,
    FEATURE_BRANCH,
    FeatureBranchScenario,
)
from praxis.modules.git.scenarios.rebase_conflict import (
    EXPECTED_SETTINGS as REBASE_CONFLICT_SETTINGS,
)
from praxis.modules.git.scenarios.rebase_conflict import RebaseConflictScenario
from praxis.modules.git.scenarios.rebase_onto_main import RebaseOntoMainScenario
from praxis.modules.git.scenarios.recover_with_reflog import RecoverWithReflogScenario
from praxis.modules.git.scenarios.selective_stage import (
    FIXED_APP_PY,
    NOTES_SCRATCH,
    SelectiveStageScenario,
)
from praxis.modules.git.scenarios.squash_feature import SquashFeatureScenario
from praxis.modules.git.scenarios.stash_context_switch import (
    FEATURE_BRANCH as STASH_FEATURE,
)
from praxis.modules.git.scenarios.stash_context_switch import (
    FIXED_README,
    StashContextSwitchScenario,
)
from praxis.modules.git.scenarios.tracking_pull import TrackingPullScenario


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    # Mimic workspace layout: parent/.praxis/hooks + repo/
    workspace = tmp_path / "ws"
    (workspace / ".praxis" / "hooks").mkdir(parents=True)
    path = workspace / "repo"
    path.mkdir()
    return path


def test_feature_branch_flow(repo: Path) -> None:
    scenario = FeatureBranchScenario()
    state = scenario.setup(repo)
    assert scenario.validate(repo, state).passed is False

    git_ops.switch_branch(repo, FEATURE_BRANCH, create=True)
    write_text(repo, README_MD, EXPECTED_README)
    write_text(repo, SETTINGS_TOML, EXPECTED_SETTINGS)
    git_ops.add_all(repo)
    git_ops.commit(repo, "Ship docs and settings")

    result = scenario.validate(repo, state)
    assert result.passed, result

    # Bypass: commit on main
    git_ops.checkout(repo, "main")
    write_text(repo, README_MD, EXPECTED_README)
    write_text(repo, SETTINGS_TOML, EXPECTED_SETTINGS)
    git_ops.add_all(repo)
    git_ops.commit(repo, "wrong branch")
    assert scenario.validate(repo, state).passed is False


def test_selective_stage_flow(repo: Path) -> None:
    scenario = SelectiveStageScenario()
    state = scenario.setup(repo)
    assert scenario.validate(repo, state).passed is False

    # Bypass: add everything
    git_ops.add_all(repo)
    git_ops.commit(repo, "too much")
    assert scenario.validate(repo, state).passed is False

    git_ops.reset(repo, state.base_sha, mode="hard")
    write_text(repo, APP_PY, FIXED_APP_PY)
    write_text(repo, SETTINGS_TOML, state.forbidden_settings)
    write_text(repo, NOTES_SCRATCH, state.forbidden_notes)
    git_ops.add_paths(repo, APP_PY)
    git_ops.commit(repo, "fix app only")
    assert scenario.validate(repo, state).passed


def test_tracking_pull_flow(repo: Path) -> None:
    scenario = TrackingPullScenario()
    state = scenario.setup(repo)
    assert scenario.validate(repo, state).passed is False
    git_ops.pull(repo, "origin", "main", ff_only=True)
    assert scenario.validate(repo, state).passed


def test_rebase_onto_main_flow(repo: Path) -> None:
    scenario = RebaseOntoMainScenario()
    state = scenario.setup(repo)
    assert scenario.validate(repo, state).passed is False

    # Bypass: merge
    git_ops.merge(repo, "main", no_edit=True)
    assert scenario.validate(repo, state).passed is False

    git_ops.reset(repo, state.pre_rebase_feature_tip, mode="hard")
    git_ops.rebase(repo, "main")
    assert scenario.validate(repo, state).passed


def test_stash_context_switch_flow(repo: Path) -> None:
    scenario = StashContextSwitchScenario()
    state = scenario.setup(repo)
    assert scenario.validate(repo, state).passed is False

    git_ops.stash_push(repo, "wip")
    git_ops.checkout(repo, "main")
    write_text(repo, README_MD, FIXED_README)
    git_ops.add_all(repo)
    git_ops.commit(repo, "hotfix readme")
    git_ops.checkout(repo, STASH_FEATURE)
    git_ops.stash_pop(repo)
    assert scenario.validate(repo, state).passed


def test_recover_with_reflog_flow(repo: Path) -> None:
    scenario = RecoverWithReflogScenario()
    state = scenario.setup(repo)
    assert scenario.validate(repo, state).passed is False
    git_ops.reset(repo, state.lost_sha, mode="hard")
    assert scenario.validate(repo, state).passed


def test_bisect_regression_flow(repo: Path) -> None:
    scenario = BisectRegressionScenario()
    state = scenario.setup(repo)
    assert scenario.validate(repo, state).passed is False
    (repo / ANSWER_FILE).write_text(state.first_bad_sha + "\n", encoding="utf-8")
    assert scenario.validate(repo, state).passed
    (repo / ANSWER_FILE).write_text(state.good_sha + "\n", encoding="utf-8")
    assert scenario.validate(repo, state).passed is False


def test_clean_merge_flow(repo: Path) -> None:
    scenario = CleanMergeScenario()
    state = scenario.setup(repo)
    assert scenario.validate(repo, state).passed is False
    git_ops.merge(repo, CLEAN_FEATURE, no_ff=True, no_edit=True)
    assert scenario.validate(repo, state).passed


def test_discard_local_flow(repo: Path) -> None:
    scenario = DiscardLocalScenario()
    state = scenario.setup(repo)
    assert scenario.validate(repo, state).passed is False
    git_ops.restore(repo, APP_PY, SETTINGS_TOML)
    assert (repo / README_MD).read_text(encoding="utf-8").replace(
        "\r\n", "\n"
    ) == KEEP_README
    assert scenario.validate(repo, state).passed


def test_rebase_conflict_flow(repo: Path) -> None:
    scenario = RebaseConflictScenario()
    state = scenario.setup(repo)
    assert scenario.validate(repo, state).passed is False
    write_text(repo, SETTINGS_TOML, REBASE_CONFLICT_SETTINGS)
    git_ops.add_all(repo)
    git_ops.rebase_continue(repo)
    assert scenario.validate(repo, state).passed


def test_cherry_pick_hotfix_flow(repo: Path) -> None:
    scenario = CherryPickHotfixScenario()
    state = scenario.setup(repo)
    assert scenario.validate(repo, state).passed is False

    # Bypass: merge whole branch
    git_ops.merge(repo, HOTFIX_BRANCH, no_edit=True)
    assert scenario.validate(repo, state).passed is False

    git_ops.reset(repo, state.release_tip_sha, mode="hard")
    git_ops.cherry_pick(repo, state.hotfix_commit_sha)
    assert scenario.validate(repo, state).passed


def test_squash_feature_flow(repo: Path) -> None:
    scenario = SquashFeatureScenario()
    state = scenario.setup(repo)
    assert scenario.validate(repo, state).passed is False
    git_ops.reset(repo, state.main_tip_sha, mode="soft")
    git_ops.commit(repo, "Squashed feature")
    assert scenario.validate(repo, state).passed


def test_diverged_remote_flow(repo: Path) -> None:
    scenario = DivergedRemoteScenario()
    state = scenario.setup(repo)
    assert scenario.validate(repo, state).passed is False
    # merge then resolve README
    result = git_ops.merge(
        repo, "origin/main", no_edit=True, allowed_returncodes={0, 1}
    )
    if result.returncode == 1:
        write_text(repo, README_MD, state.expected_readme)
        git_ops.add_all(repo)
        git_ops.commit(repo, "Merge origin/main")
    else:
        # unlikely without conflict given divergent README
        write_text(repo, README_MD, state.expected_readme)
        git_ops.add_all(repo)
        git_ops.commit(repo, "Combine README notes")
    assert scenario.validate(repo, state).passed


def test_state_round_trips(tmp_path: Path) -> None:
    for index, scenario in enumerate(
        (
            FeatureBranchScenario(),
            SelectiveStageScenario(),
            TrackingPullScenario(),
            RebaseOntoMainScenario(),
            StashContextSwitchScenario(),
            RecoverWithReflogScenario(),
            BisectRegressionScenario(),
        )
    ):
        workspace = tmp_path / f"ws{index}"
        (workspace / ".praxis" / "hooks").mkdir(parents=True)
        repo = workspace / "repo"
        repo.mkdir()
        state = scenario.setup(repo)
        raw = state.model_dump(mode="json")
        rehydrated = scenario.state_model.model_validate(raw)
        assert rehydrated == state
