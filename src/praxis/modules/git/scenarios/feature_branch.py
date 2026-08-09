"""Git feature-branch training scenario."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict

from praxis.errors import ProcessError, ScenarioSetupError
from praxis.models import Assignment, CheckResult, ObjectiveResult
from praxis.modules.git import git_ops
from praxis.modules.git.configsvc import (
    README_MD,
    SETTINGS_TOML,
    init_configsvc_repo,
    read_text_normalized,
    show_file_at,
    write_text,
)

FEATURE_BRANCH = "feature/readme-settings"

EXPECTED_README = """\
# configsvc

Tiny settings helper used by Praxis Git labs.

## Defaults

Default timeout is configurable in `settings.toml`.
"""

EXPECTED_SETTINGS = """\
# configsvc settings
timeout_ms = 2500
log_level = "info"
"""


class FeatureBranchState(BaseModel):
    """Immutable facts recorded when feature-branch setup completes."""

    model_config = ConfigDict(frozen=True)

    main_tip_sha: str
    expected_readme: str
    expected_settings: str


class FeatureBranchScenario:
    """Create a feature branch and commit README + settings changes there."""

    id: str = "feature-branch"
    module: str = "git"
    title: str = "Ship work on a feature branch"
    description: str = (
        "Create a feature branch and commit README and settings changes "
        "without moving main."
    )
    difficulty: str | None = "beginner"
    concepts: list[str] = ["branch", "commit", "switch"]
    state_model: type[FeatureBranchState] = FeatureBranchState

    def assignment(self) -> Assignment:
        return Assignment(
            title=self.title,
            summary=(
                "You need a README improvement and a new default timeout in "
                "`settings.toml`. Do that work on branch "
                f"`{FEATURE_BRANCH}` so `main` stays exactly where setup left it. "
                "Commit the finished files on the feature branch and leave a "
                "clean working tree."
            ),
            objectives=[
                f"Create and check out branch `{FEATURE_BRANCH}`.",
                "Commit the required README.md and settings.toml contents on "
                "that branch.",
                "Leave branch `main` at its original tip.",
                "Leave a clean working tree.",
            ],
        )

    def setup(self, repo_path: Path) -> FeatureBranchState:
        main_tip_sha = init_configsvc_repo(repo_path)
        state = FeatureBranchState(
            main_tip_sha=main_tip_sha,
            expected_readme=EXPECTED_README,
            expected_settings=EXPECTED_SETTINGS,
        )
        self._verify_setup(repo_path, state)
        return state

    def _verify_setup(self, repo_path: Path, state: FeatureBranchState) -> None:
        errors: list[str] = []
        if git_ops.is_detached_head(repo_path):
            errors.append("HEAD is detached; expected branch main")
        elif git_ops.current_branch(repo_path) != "main":
            errors.append(f"HEAD is on {git_ops.current_branch(repo_path)!r}")
        if git_ops.rev_parse(repo_path, "HEAD") != state.main_tip_sha:
            errors.append("HEAD does not match recorded main_tip_sha")
        if not git_ops.is_clean(repo_path):
            errors.append("Expected a clean working tree after setup")
        if git_ops.rev_parse_verify(repo_path, FEATURE_BRANCH) is not None:
            errors.append(f"Branch {FEATURE_BRANCH} must not exist yet")
        if errors:
            raise ScenarioSetupError(
                "feature-branch setup postconditions failed:\n- "
                + "\n- ".join(errors)
            )

    def validate(
        self, repo_path: Path, state: FeatureBranchState
    ) -> CheckResult:
        objectives = [
            self._check_on_feature(repo_path),
            self._check_main_unchanged(repo_path, state),
            self._check_feature_ahead(repo_path, state),
            self._check_readme(repo_path, state),
            self._check_settings(repo_path, state),
            self._check_clean(repo_path),
        ]
        return CheckResult(
            passed=all(item.passed for item in objectives),
            objectives=objectives,
        )

    def _check_on_feature(self, repo_path: Path) -> ObjectiveResult:
        if git_ops.is_detached_head(repo_path):
            return ObjectiveResult(
                id="on-feature",
                description=f"HEAD is attached to {FEATURE_BRANCH}",
                passed=False,
                detail="HEAD is detached",
            )
        branch = git_ops.current_branch(repo_path)
        passed = branch == FEATURE_BRANCH
        return ObjectiveResult(
            id="on-feature",
            description=f"HEAD is attached to {FEATURE_BRANCH}",
            passed=passed,
            detail=None if passed else f"HEAD is on {branch!r}",
        )

    def _check_main_unchanged(
        self, repo_path: Path, state: FeatureBranchState
    ) -> ObjectiveResult:
        try:
            main_sha = git_ops.rev_parse(repo_path, "main")
        except ProcessError as exc:
            return ObjectiveResult(
                id="main-unchanged",
                description="Branch main still points at the setup tip",
                passed=False,
                detail=exc.message,
            )
        passed = main_sha == state.main_tip_sha
        return ObjectiveResult(
            id="main-unchanged",
            description="Branch main still points at the setup tip",
            passed=passed,
            detail=None
            if passed
            else f"main={main_sha}, expected={state.main_tip_sha}",
        )

    def _check_feature_ahead(
        self, repo_path: Path, state: FeatureBranchState
    ) -> ObjectiveResult:
        head = git_ops.rev_parse_verify(repo_path, "HEAD")
        if head is None:
            return ObjectiveResult(
                id="feature-ahead",
                description="Feature branch tip differs from main",
                passed=False,
                detail="HEAD does not resolve",
            )
        passed = head != state.main_tip_sha
        return ObjectiveResult(
            id="feature-ahead",
            description="Feature branch tip differs from main",
            passed=passed,
            detail=None if passed else "HEAD still matches main tip",
        )

    def _check_readme(
        self, repo_path: Path, state: FeatureBranchState
    ) -> ObjectiveResult:
        actual = show_file_at(repo_path, "HEAD", README_MD)
        passed = actual == state.expected_readme
        return ObjectiveResult(
            id="readme-content",
            description="README.md at HEAD matches the required content",
            passed=passed,
            detail=None if passed else "README.md content does not match",
        )

    def _check_settings(
        self, repo_path: Path, state: FeatureBranchState
    ) -> ObjectiveResult:
        actual = show_file_at(repo_path, "HEAD", SETTINGS_TOML)
        passed = actual == state.expected_settings
        return ObjectiveResult(
            id="settings-content",
            description="settings.toml at HEAD matches the required content",
            passed=passed,
            detail=None if passed else "settings.toml content does not match",
        )

    def _check_clean(self, repo_path: Path) -> ObjectiveResult:
        passed = git_ops.is_clean(repo_path)
        return ObjectiveResult(
            id="clean-tree",
            description="Working tree is clean",
            passed=passed,
            detail=None
            if passed
            else f"Dirty paths:\n{git_ops.status_porcelain(repo_path).rstrip()}",
        )


# Re-export helpers used by tests for convenient content writes.
__all__ = [
    "EXPECTED_README",
    "EXPECTED_SETTINGS",
    "FEATURE_BRANCH",
    "FeatureBranchScenario",
    "FeatureBranchState",
    "read_text_normalized",
    "write_text",
]
