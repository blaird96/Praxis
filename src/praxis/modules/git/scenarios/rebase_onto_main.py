"""Git rebase-onto-main training scenario."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict

from praxis.errors import ScenarioSetupError
from praxis.models import Assignment, CheckResult, ObjectiveResult
from praxis.modules.git import git_ops
from praxis.modules.git.configsvc import (
    APP_PY,
    README_MD,
    SETTINGS_TOML,
    init_configsvc_repo,
    show_file_at,
    write_text,
)

FEATURE_BRANCH = "feature/api-timeout"

MAIN_README = """\
# configsvc

Tiny settings helper used by Praxis Git labs.

Mainline note: health endpoint planned.
"""

FEATURE_APP = '''\
"""Minimal settings service for Praxis labs."""

from pathlib import Path

DEFAULT_TIMEOUT_MS = 1000
API_TIMEOUT_MS = 3000


def load_settings(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"')
    return values


def timeout_ms(settings: dict[str, str]) -> int:
    raw = settings.get("timeout_ms", str(DEFAULT_TIMEOUT_MS))
    return int(raw)


def api_timeout_ms() -> int:
    return API_TIMEOUT_MS
'''

FEATURE_SETTINGS = """\
# configsvc settings
timeout_ms = 1000
log_level = "info"
api_timeout_ms = 3000
"""


class RebaseOntoMainState(BaseModel):
    model_config = ConfigDict(frozen=True)

    main_tip_sha: str
    pre_rebase_feature_tip: str
    expected_app: str
    expected_settings: str
    expected_readme: str


class RebaseOntoMainScenario:
    """Rebase a feature branch onto an updated main without merge commits."""

    id: str = "rebase-onto-main"
    module: str = "git"
    title: str = "Rebase a feature branch onto updated main"
    description: str = (
        "main moved while you worked on a feature branch. Replay your commits "
        "onto the latest main without creating a merge commit."
    )
    difficulty: str | None = "intermediate"
    concepts: list[str] = ["rebase", "linear-history", "merge-base"]
    state_model: type[RebaseOntoMainState] = RebaseOntoMainState

    def assignment(self) -> Assignment:
        return Assignment(
            title=self.title,
            summary=(
                f"Branch `{FEATURE_BRANCH}` diverged from `main`. `main` now "
                "includes a README update you need underneath your API timeout "
                "work. Replay your feature commits onto the latest `main` so "
                "history is linear, `main` itself stays put, and your feature "
                "file changes remain."
            ),
            objectives=[
                f"Remain on `{FEATURE_BRANCH}`.",
                "Leave branch `main` at its recorded tip.",
                "Recorded main tip is an ancestor of HEAD.",
                "HEAD is not a merge commit and contains the feature + main content.",
            ],
        )

    def setup(self, repo_path: Path) -> RebaseOntoMainState:
        init_configsvc_repo(repo_path)
        git_ops.create_branch(repo_path, FEATURE_BRANCH)

        write_text(repo_path, README_MD, MAIN_README)
        git_ops.add_all(repo_path)
        main_tip_sha = git_ops.commit(repo_path, "Document health endpoint plan")

        git_ops.checkout(repo_path, FEATURE_BRANCH)
        write_text(repo_path, APP_PY, FEATURE_APP)
        git_ops.add_all(repo_path)
        git_ops.commit(repo_path, "Add API timeout helper")
        write_text(repo_path, SETTINGS_TOML, FEATURE_SETTINGS)
        git_ops.add_all(repo_path)
        pre_rebase_feature_tip = git_ops.commit(
            repo_path, "Expose api_timeout_ms setting"
        )

        state = RebaseOntoMainState(
            main_tip_sha=main_tip_sha,
            pre_rebase_feature_tip=pre_rebase_feature_tip,
            expected_app=FEATURE_APP,
            expected_settings=FEATURE_SETTINGS,
            expected_readme=MAIN_README,
        )
        self._verify_setup(repo_path, state)
        return state

    def _verify_setup(self, repo_path: Path, state: RebaseOntoMainState) -> None:
        errors: list[str] = []
        if git_ops.current_branch(repo_path) != FEATURE_BRANCH:
            errors.append(f"Expected checkout on {FEATURE_BRANCH}")
        if git_ops.rev_parse(repo_path, "main") != state.main_tip_sha:
            errors.append("main tip mismatch")
        if git_ops.rev_parse(repo_path, "HEAD") != state.pre_rebase_feature_tip:
            errors.append("feature tip mismatch")
        if git_ops.is_ancestor(repo_path, state.main_tip_sha, "HEAD"):
            errors.append("feature should not already contain main tip")
        if not git_ops.is_clean(repo_path):
            errors.append("Expected clean tree")
        if errors:
            raise ScenarioSetupError(
                "rebase-onto-main setup postconditions failed:\n- "
                + "\n- ".join(errors)
            )

    def validate(
        self, repo_path: Path, state: RebaseOntoMainState
    ) -> CheckResult:
        objectives = [
            self._check_on_feature(repo_path),
            self._check_main_unchanged(repo_path, state),
            self._check_ancestor(repo_path, state),
            self._check_linear(repo_path),
            self._check_content(repo_path, state),
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
        self, repo_path: Path, state: RebaseOntoMainState
    ) -> ObjectiveResult:
        main_sha = git_ops.rev_parse(repo_path, "main")
        passed = main_sha == state.main_tip_sha
        return ObjectiveResult(
            id="main-unchanged",
            description="Branch main still points at the setup tip",
            passed=passed,
            detail=None
            if passed
            else f"main={main_sha}, expected={state.main_tip_sha}",
        )

    def _check_ancestor(
        self, repo_path: Path, state: RebaseOntoMainState
    ) -> ObjectiveResult:
        passed = git_ops.is_ancestor(repo_path, state.main_tip_sha, "HEAD")
        return ObjectiveResult(
            id="main-ancestor",
            description="Recorded main tip is an ancestor of HEAD",
            passed=passed,
            detail=None if passed else "main tip is not an ancestor of HEAD",
        )

    def _check_linear(self, repo_path: Path) -> ObjectiveResult:
        parents = git_ops.commit_parents(repo_path, "HEAD")
        passed = len(parents) == 1
        return ObjectiveResult(
            id="linear-tip",
            description="HEAD is not a merge commit",
            passed=passed,
            detail=None if passed else f"HEAD has {len(parents)} parents",
        )

    def _check_content(
        self, repo_path: Path, state: RebaseOntoMainState
    ) -> ObjectiveResult:
        app = show_file_at(repo_path, "HEAD", APP_PY)
        settings = show_file_at(repo_path, "HEAD", SETTINGS_TOML)
        readme = show_file_at(repo_path, "HEAD", README_MD)
        passed = (
            app == state.expected_app
            and settings == state.expected_settings
            and readme == state.expected_readme
        )
        return ObjectiveResult(
            id="rebased-content",
            description="HEAD contains both main README and feature changes",
            passed=passed,
            detail=None if passed else "One or more expected files do not match",
        )

    def _check_clean(self, repo_path: Path) -> ObjectiveResult:
        passed = git_ops.is_clean(repo_path) and not git_ops.rebase_in_progress(
            repo_path
        )
        return ObjectiveResult(
            id="clean-tree",
            description="Working tree is clean and no rebase is in progress",
            passed=passed,
            detail=None if passed else "Dirty tree or rebase still in progress",
        )
