"""Git squash-feature training scenario."""

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

FEATURE_BRANCH = "feature/noisy"


class SquashFeatureState(BaseModel):
    model_config = ConfigDict(frozen=True)

    main_tip_sha: str
    expected_app: str
    expected_settings: str
    expected_readme: str
    pre_squash_commit_count: int


class SquashFeatureScenario:
    """Collapse multiple feature commits into a single commit on the feature branch."""

    id: str = "squash-feature"
    module: str = "git"
    title: str = "Collapse noisy feature commits before merge"
    description: str = (
        "A feature branch has several noisy commits. Squash them into one "
        "commit on top of main before review."
    )
    difficulty: str | None = "intermediate"
    concepts: list[str] = ["squash", "reset", "rebase"]
    state_model: type[SquashFeatureState] = SquashFeatureState

    def assignment(self) -> Assignment:
        return Assignment(
            title=self.title,
            summary=(
                f"Branch `{FEATURE_BRANCH}` has multiple WIP commits. Collapse "
                "them into a single commit whose parent is the recorded `main` "
                "tip, preserving the final app/settings/README contents, with "
                "a clean tree."
            ),
            objectives=[
                f"Remain on `{FEATURE_BRANCH}`.",
                "HEAD has exactly one commit on top of main.",
                "Final file contents match the pre-squash tip tree.",
                "Working tree is clean.",
            ],
        )

    def setup(self, repo_path: Path) -> SquashFeatureState:
        main_tip_sha = init_configsvc_repo(repo_path)
        git_ops.switch_branch(repo_path, FEATURE_BRANCH, create=True)

        app1 = (repo_path / APP_PY).read_text(encoding="utf-8").replace(
            "DEFAULT_TIMEOUT_MS = 1000", "DEFAULT_TIMEOUT_MS = 1100"
        )
        write_text(repo_path, APP_PY, app1)
        git_ops.add_all(repo_path)
        git_ops.commit(repo_path, "WIP 1")

        write_text(
            repo_path,
            SETTINGS_TOML,
            '# configsvc settings\ntimeout_ms = 1100\nlog_level = "info"\n',
        )
        git_ops.add_all(repo_path)
        git_ops.commit(repo_path, "WIP 2")

        write_text(
            repo_path,
            README_MD,
            "# configsvc\n\nSquashed feature ready.\n",
        )
        git_ops.add_all(repo_path)
        tip = git_ops.commit(repo_path, "WIP 3")

        expected_app = git_ops.show(repo_path, f"{tip}:{APP_PY}").replace(
            "\r\n", "\n"
        )
        expected_settings = git_ops.show(
            repo_path, f"{tip}:{SETTINGS_TOML}"
        ).replace("\r\n", "\n")
        expected_readme = git_ops.show(repo_path, f"{tip}:{README_MD}").replace(
            "\r\n", "\n"
        )
        count = len(git_ops.rev_list(repo_path, f"{main_tip_sha}..HEAD"))

        state = SquashFeatureState(
            main_tip_sha=main_tip_sha,
            expected_app=expected_app,
            expected_settings=expected_settings,
            expected_readme=expected_readme,
            pre_squash_commit_count=count,
        )
        self._verify_setup(repo_path, state)
        return state

    def _verify_setup(self, repo_path: Path, state: SquashFeatureState) -> None:
        errors: list[str] = []
        if state.pre_squash_commit_count < 3:
            errors.append("expected at least 3 feature commits")
        if git_ops.current_branch(repo_path) != FEATURE_BRANCH:
            errors.append("expected feature branch")
        if errors:
            raise ScenarioSetupError(
                "squash-feature setup postconditions failed:\n- "
                + "\n- ".join(errors)
            )

    def validate(self, repo_path: Path, state: SquashFeatureState) -> CheckResult:
        objectives = [
            self._on_feature(repo_path),
            self._one_commit(repo_path, state),
            self._content(repo_path, state),
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

    def _one_commit(
        self, repo_path: Path, state: SquashFeatureState
    ) -> ObjectiveResult:
        parents = git_ops.commit_parents(repo_path, "HEAD")
        count = len(git_ops.rev_list(repo_path, f"{state.main_tip_sha}..HEAD"))
        passed = parents == [state.main_tip_sha] and count == 1
        return ObjectiveResult(
            id="single-commit",
            description="Exactly one commit on top of main",
            passed=passed,
            detail=None if passed else f"count={count}, parents={parents}",
        )

    def _content(
        self, repo_path: Path, state: SquashFeatureState
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
            id="squashed-content",
            description="Final tree matches pre-squash tip contents",
            passed=passed,
            detail=None if passed else "content mismatch",
        )

    def _clean(self, repo_path: Path) -> ObjectiveResult:
        passed = git_ops.is_clean(repo_path)
        return ObjectiveResult(
            id="clean-tree",
            description="Working tree is clean",
            passed=passed,
            detail=None if passed else git_ops.status_porcelain(repo_path),
        )
