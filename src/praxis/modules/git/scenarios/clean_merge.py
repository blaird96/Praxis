"""Git clean-merge training scenario."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict

from praxis.errors import ScenarioSetupError
from praxis.models import Assignment, CheckResult, ObjectiveResult
from praxis.modules.git import git_ops
from praxis.modules.git.configsvc import (
    README_MD,
    init_configsvc_repo,
    show_file_at,
    write_text,
)

FEATURE_BRANCH = "feature/docs"

FEATURE_README = """\
# configsvc

Tiny settings helper used by Praxis Git labs.

## Usage

Import `load_settings` from `app`.
"""


class CleanMergeState(BaseModel):
    model_config = ConfigDict(frozen=True)

    main_tip_sha: str
    feature_tip_sha: str
    expected_readme: str


class CleanMergeScenario:
    """Merge a finished feature branch into main without conflicts."""

    id: str = "clean-merge"
    module: str = "git"
    title: str = "Merge a finished feature without conflicts"
    description: str = (
        "Integrate a completed documentation feature into main with a real "
        "merge commit."
    )
    difficulty: str | None = "beginner"
    concepts: list[str] = ["merge", "merge-commit"]
    state_model: type[CleanMergeState] = CleanMergeState

    def assignment(self) -> Assignment:
        return Assignment(
            title=self.title,
            summary=(
                f"Branch `{FEATURE_BRANCH}` adds README usage docs and is ready "
                "to land. Merge it into `main` so history records a two-parent "
                "merge commit, README matches the feature tip, and the tree is "
                "clean."
            ),
            objectives=[
                "Remain on `main` with a completed merge.",
                "HEAD is a merge commit whose parents are the recorded tips.",
                "README.md matches the feature content.",
                "Working tree is clean.",
            ],
        )

    def setup(self, repo_path: Path) -> CleanMergeState:
        main_tip_sha = init_configsvc_repo(repo_path)
        git_ops.switch_branch(repo_path, FEATURE_BRANCH, create=True)
        write_text(repo_path, README_MD, FEATURE_README)
        git_ops.add_all(repo_path)
        feature_tip_sha = git_ops.commit(repo_path, "Document usage")
        git_ops.checkout(repo_path, "main")
        state = CleanMergeState(
            main_tip_sha=main_tip_sha,
            feature_tip_sha=feature_tip_sha,
            expected_readme=FEATURE_README,
        )
        self._verify_setup(repo_path, state)
        return state

    def _verify_setup(self, repo_path: Path, state: CleanMergeState) -> None:
        errors: list[str] = []
        if git_ops.current_branch(repo_path) != "main":
            errors.append("Expected main")
        if git_ops.merge_head_exists(repo_path):
            errors.append("Merge should not be in progress yet")
        if not git_ops.is_clean(repo_path):
            errors.append("Expected clean tree")
        if errors:
            raise ScenarioSetupError(
                "clean-merge setup postconditions failed:\n- "
                + "\n- ".join(errors)
            )

    def validate(self, repo_path: Path, state: CleanMergeState) -> CheckResult:
        objectives = [
            self._on_main(repo_path),
            self._merge_done(repo_path),
            self._merge_commit(repo_path, state),
            self._readme(repo_path, state),
            self._clean(repo_path),
        ]
        return CheckResult(
            passed=all(o.passed for o in objectives), objectives=objectives
        )

    def _on_main(self, repo_path: Path) -> ObjectiveResult:
        if git_ops.is_detached_head(repo_path):
            return ObjectiveResult(
                id="on-main",
                description="HEAD is attached to main",
                passed=False,
                detail="detached",
            )
        branch = git_ops.current_branch(repo_path)
        return ObjectiveResult(
            id="on-main",
            description="HEAD is attached to main",
            passed=branch == "main",
            detail=None if branch == "main" else f"on {branch}",
        )

    def _merge_done(self, repo_path: Path) -> ObjectiveResult:
        passed = not git_ops.merge_head_exists(repo_path)
        return ObjectiveResult(
            id="merge-finished",
            description="Merge is finished",
            passed=passed,
            detail=None if passed else "MERGE_HEAD present",
        )

    def _merge_commit(
        self, repo_path: Path, state: CleanMergeState
    ) -> ObjectiveResult:
        parents = git_ops.commit_parents(repo_path, "HEAD")
        passed = (
            len(parents) == 2
            and parents[0] == state.main_tip_sha
            and parents[1] == state.feature_tip_sha
        )
        return ObjectiveResult(
            id="merge-parents",
            description="Merge parents match recorded tips",
            passed=passed,
            detail=None if passed else f"parents={parents}",
        )

    def _readme(
        self, repo_path: Path, state: CleanMergeState
    ) -> ObjectiveResult:
        actual = show_file_at(repo_path, "HEAD", README_MD)
        passed = actual == state.expected_readme
        return ObjectiveResult(
            id="readme-content",
            description="README matches feature content",
            passed=passed,
            detail=None if passed else "README mismatch",
        )

    def _clean(self, repo_path: Path) -> ObjectiveResult:
        passed = git_ops.is_clean(repo_path)
        return ObjectiveResult(
            id="clean-tree",
            description="Working tree is clean",
            passed=passed,
            detail=None if passed else git_ops.status_porcelain(repo_path),
        )
