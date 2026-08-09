"""Git rebase-conflict training scenario."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict

from praxis.errors import ScenarioSetupError
from praxis.models import Assignment, CheckResult, ObjectiveResult
from praxis.modules.git import git_ops
from praxis.modules.git.configsvc import (
    SETTINGS_TOML,
    init_configsvc_repo,
    read_text_normalized,
    show_file_at,
    write_text,
)

FEATURE_BRANCH = "feature/log-level"

MAIN_SETTINGS = """\
# configsvc settings
timeout_ms = 1000
log_level = "warn"
"""

FEATURE_SETTINGS = """\
# configsvc settings
timeout_ms = 1000
log_level = "debug"
"""

EXPECTED_SETTINGS = """\
# configsvc settings
timeout_ms = 1000
log_level = "debug"
"""


class RebaseConflictState(BaseModel):
    model_config = ConfigDict(frozen=True)

    main_tip_sha: str
    pre_rebase_feature_tip: str
    expected_settings: str


class RebaseConflictScenario:
    """Finish a conflicted rebase of a feature branch onto main."""

    id: str = "rebase-conflict"
    module: str = "git"
    title: str = "Finish a conflicted rebase"
    description: str = (
        "Rebasing a feature branch onto main conflicted in settings.toml. "
        "Resolve it and continue the rebase."
    )
    difficulty: str | None = "intermediate"
    concepts: list[str] = ["rebase", "conflict-resolution"]
    state_model: type[RebaseConflictState] = RebaseConflictState

    def assignment(self) -> Assignment:
        return Assignment(
            title=self.title,
            summary=(
                f"A rebase of `{FEATURE_BRANCH}` onto `main` is already in "
                "progress and conflicted in `settings.toml`. Prefer the feature "
                "branch log_level (`debug`), finish the rebase, and leave a "
                "linear history with `main` unchanged."
            ),
            objectives=[
                f"Remain on `{FEATURE_BRANCH}` with rebase finished.",
                "Recorded main tip is an ancestor of HEAD.",
                "settings.toml has log_level debug.",
                "Working tree is clean.",
            ],
        )

    def setup(self, repo_path: Path) -> RebaseConflictState:
        init_configsvc_repo(repo_path)
        git_ops.create_branch(repo_path, FEATURE_BRANCH)

        write_text(repo_path, SETTINGS_TOML, MAIN_SETTINGS)
        git_ops.add_all(repo_path)
        main_tip_sha = git_ops.commit(repo_path, "Raise default log level to warn")

        git_ops.checkout(repo_path, FEATURE_BRANCH)
        write_text(repo_path, SETTINGS_TOML, FEATURE_SETTINGS)
        git_ops.add_all(repo_path)
        pre_rebase_feature_tip = git_ops.commit(
            repo_path, "Use debug logging on feature"
        )

        result = git_ops.rebase(
            repo_path, "main", allowed_returncodes={0, 1}
        )
        if result.returncode == 0:
            raise ScenarioSetupError("Expected rebase to conflict")
        if not git_ops.rebase_in_progress(repo_path):
            raise ScenarioSetupError("Expected rebase in progress after conflict")

        state = RebaseConflictState(
            main_tip_sha=main_tip_sha,
            pre_rebase_feature_tip=pre_rebase_feature_tip,
            expected_settings=EXPECTED_SETTINGS,
        )
        self._verify_setup(repo_path, state)
        return state

    def _verify_setup(self, repo_path: Path, state: RebaseConflictState) -> None:
        errors: list[str] = []
        if not git_ops.rebase_in_progress(repo_path):
            errors.append("rebase not in progress")
        if not git_ops.has_unmerged_paths(repo_path):
            errors.append("expected unmerged paths")
        text = read_text_normalized(repo_path, SETTINGS_TOML)
        if "<<<<<<<" not in text:
            errors.append("expected conflict markers")
        if errors:
            raise ScenarioSetupError(
                "rebase-conflict setup postconditions failed:\n- "
                + "\n- ".join(errors)
            )

    def validate(self, repo_path: Path, state: RebaseConflictState) -> CheckResult:
        objectives = [
            self._on_feature(repo_path),
            self._rebase_done(repo_path),
            self._main_ancestor(repo_path, state),
            self._settings(repo_path, state),
            self._main_unchanged(repo_path, state),
            self._clean(repo_path),
        ]
        return CheckResult(
            passed=all(o.passed for o in objectives), objectives=objectives
        )

    def _on_feature(self, repo_path: Path) -> ObjectiveResult:
        if git_ops.is_detached_head(repo_path):
            return ObjectiveResult(
                id="on-feature",
                description=f"On {FEATURE_BRANCH}",
                passed=False,
                detail="detached",
            )
        branch = git_ops.current_branch(repo_path)
        return ObjectiveResult(
            id="on-feature",
            description=f"On {FEATURE_BRANCH}",
            passed=branch == FEATURE_BRANCH,
            detail=None if branch == FEATURE_BRANCH else branch,
        )

    def _rebase_done(self, repo_path: Path) -> ObjectiveResult:
        passed = not git_ops.rebase_in_progress(repo_path)
        return ObjectiveResult(
            id="rebase-finished",
            description="Rebase is finished",
            passed=passed,
            detail=None if passed else "rebase still in progress",
        )

    def _main_ancestor(
        self, repo_path: Path, state: RebaseConflictState
    ) -> ObjectiveResult:
        passed = git_ops.is_ancestor(repo_path, state.main_tip_sha, "HEAD")
        return ObjectiveResult(
            id="main-ancestor",
            description="main tip is an ancestor of HEAD",
            passed=passed,
            detail=None if passed else "main tip not ancestor",
        )

    def _settings(
        self, repo_path: Path, state: RebaseConflictState
    ) -> ObjectiveResult:
        actual = show_file_at(repo_path, "HEAD", SETTINGS_TOML)
        passed = actual == state.expected_settings
        return ObjectiveResult(
            id="settings-content",
            description="settings.toml resolved to debug log_level",
            passed=passed,
            detail=None if passed else "settings mismatch",
        )

    def _main_unchanged(
        self, repo_path: Path, state: RebaseConflictState
    ) -> ObjectiveResult:
        main = git_ops.rev_parse(repo_path, "main")
        passed = main == state.main_tip_sha
        return ObjectiveResult(
            id="main-unchanged",
            description="main tip unchanged",
            passed=passed,
            detail=None if passed else main,
        )

    def _clean(self, repo_path: Path) -> ObjectiveResult:
        passed = git_ops.is_clean(repo_path) and not git_ops.has_unmerged_paths(
            repo_path
        )
        return ObjectiveResult(
            id="clean-tree",
            description="Clean tree with no unmerged paths",
            passed=passed,
            detail=None if passed else git_ops.status_porcelain(repo_path),
        )
