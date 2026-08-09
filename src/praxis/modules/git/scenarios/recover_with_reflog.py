"""Git recover-with-reflog training scenario."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict

from praxis.errors import ScenarioSetupError
from praxis.models import Assignment, CheckResult, ObjectiveResult
from praxis.modules.git import git_ops
from praxis.modules.git.configsvc import (
    APP_PY,
    init_configsvc_repo,
    show_file_at,
    write_text,
)

RECOVERED_APP = '''\
"""Minimal settings service for Praxis labs."""

from pathlib import Path

DEFAULT_TIMEOUT_MS = 1000
API_TIMEOUT_MS = 4500


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


class RecoverWithReflogState(BaseModel):
    model_config = ConfigDict(frozen=True)

    lost_sha: str
    post_reset_sha: str
    lost_tree_sha: str
    expected_app: str


class RecoverWithReflogScenario:
    """Recover a commit lost to a hard reset using reflog or equivalent."""

    id: str = "recover-with-reflog"
    module: str = "git"
    title: str = "Recover a commit after a bad reset"
    description: str = (
        "A hard reset dropped a good API timeout commit. Recover that commit "
        "onto main so the tree matches the lost tip."
    )
    difficulty: str | None = "advanced"
    concepts: list[str] = ["reflog", "reset", "recovery"]
    state_model: type[RecoverWithReflogState] = RecoverWithReflogState

    def assignment(self) -> Assignment:
        return Assignment(
            title=self.title,
            summary=(
                "You accidentally reset `main` and lost the commit that added "
                "the API timeout helper (`API_TIMEOUT_MS = 4500`). Recover that "
                "work onto `main` so the branch tip's tree matches the lost "
                "commit, with a clean working tree. The lost commit is still "
                "reachable through Git's safety nets."
            ),
            objectives=[
                "Remain on branch `main`.",
                "HEAD's tree matches the lost commit's tree.",
                "Working tree is clean.",
            ],
        )

    def setup(self, repo_path: Path) -> RecoverWithReflogState:
        post_reset_sha = init_configsvc_repo(repo_path)
        write_text(repo_path, APP_PY, RECOVERED_APP)
        git_ops.add_all(repo_path)
        lost_sha = git_ops.commit(repo_path, "Add API timeout helper")
        lost_tree_sha = git_ops.commit_tree_sha(repo_path, lost_sha)
        git_ops.reset(repo_path, post_reset_sha, mode="hard")

        state = RecoverWithReflogState(
            lost_sha=lost_sha,
            post_reset_sha=post_reset_sha,
            lost_tree_sha=lost_tree_sha,
            expected_app=RECOVERED_APP,
        )
        self._verify_setup(repo_path, state)
        return state

    def _verify_setup(
        self, repo_path: Path, state: RecoverWithReflogState
    ) -> None:
        errors: list[str] = []
        if git_ops.rev_parse(repo_path, "HEAD") != state.post_reset_sha:
            errors.append("HEAD should be at post_reset_sha")
        if git_ops.rev_parse(repo_path, state.lost_sha) != state.lost_sha:
            errors.append("lost_sha must still resolve")
        reflog_text = "\n".join(git_ops.reflog(repo_path))
        if state.lost_sha[:7] not in reflog_text and state.lost_sha not in reflog_text:
            errors.append("lost_sha missing from reflog")
        if show_file_at(repo_path, "HEAD", APP_PY) == state.expected_app:
            errors.append("Lost content should not be on HEAD yet")
        if errors:
            raise ScenarioSetupError(
                "recover-with-reflog setup postconditions failed:\n- "
                + "\n- ".join(errors)
            )

    def validate(
        self, repo_path: Path, state: RecoverWithReflogState
    ) -> CheckResult:
        objectives = [
            self._check_on_main(repo_path),
            self._check_tree(repo_path, state),
            self._check_app(repo_path, state),
            self._check_clean(repo_path),
        ]
        return CheckResult(
            passed=all(item.passed for item in objectives),
            objectives=objectives,
        )

    def _check_on_main(self, repo_path: Path) -> ObjectiveResult:
        if git_ops.is_detached_head(repo_path):
            return ObjectiveResult(
                id="on-main",
                description="HEAD is attached to branch main",
                passed=False,
                detail="HEAD is detached",
            )
        branch = git_ops.current_branch(repo_path)
        passed = branch == "main"
        return ObjectiveResult(
            id="on-main",
            description="HEAD is attached to branch main",
            passed=passed,
            detail=None if passed else f"HEAD is on {branch!r}",
        )

    def _check_tree(
        self, repo_path: Path, state: RecoverWithReflogState
    ) -> ObjectiveResult:
        head_tree = git_ops.commit_tree_sha(repo_path, "HEAD")
        lost_is_ancestor = git_ops.is_ancestor(repo_path, state.lost_sha, "HEAD")
        passed = head_tree == state.lost_tree_sha or lost_is_ancestor
        return ObjectiveResult(
            id="recovered-tree",
            description="HEAD recovers the lost commit tree (or contains it)",
            passed=passed,
            detail=None
            if passed
            else f"tree={head_tree}, expected={state.lost_tree_sha}",
        )

    def _check_app(
        self, repo_path: Path, state: RecoverWithReflogState
    ) -> ObjectiveResult:
        actual = show_file_at(repo_path, "HEAD", APP_PY)
        passed = actual == state.expected_app
        return ObjectiveResult(
            id="app-content",
            description="HEAD app.py matches the recovered API timeout fix",
            passed=passed,
            detail=None if passed else "app.py does not match lost commit",
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
