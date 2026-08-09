"""Git tracking-pull training scenario."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict

from praxis.errors import ProcessError, ScenarioSetupError
from praxis.models import Assignment, CheckResult, ObjectiveResult
from praxis.modules.git import git_ops
from praxis.modules.git.configsvc import (
    README_MD,
    SETTINGS_TOML,
    hooks_path_for_repo,
    init_configsvc_repo,
    show_file_at,
    write_text,
)

REMOTE_README = """\
# configsvc

Tiny settings helper used by Praxis Git labs.

Updated from origin - please pull.
"""

REMOTE_SETTINGS = """\
# configsvc settings
timeout_ms = 1200
log_level = "info"
"""


class TrackingPullState(BaseModel):
    """Immutable facts recorded when tracking-pull setup completes."""

    model_config = ConfigDict(frozen=True)

    local_old_sha: str
    origin_main_tip_sha: str
    expected_readme: str
    expected_settings: str


class TrackingPullScenario:
    """Fast-forward local main to match origin/main."""

    id: str = "tracking-pull"
    module: str = "git"
    title: str = "Bring remote updates onto your branch"
    description: str = (
        "Local main is behind origin/main. Fast-forward to pick up teammate "
        "commits without creating a merge commit."
    )
    difficulty: str | None = "beginner"
    concepts: list[str] = ["fetch", "pull", "remote-tracking", "fast-forward"]
    state_model: type[TrackingPullState] = TrackingPullState

    def assignment(self) -> Assignment:
        return Assignment(
            title=self.title,
            summary=(
                "Teammates pushed README and settings updates to `origin/main`. "
                "Your local `main` is behind and tracks that remote branch. "
                "Update local `main` so it matches `origin/main` with a "
                "fast-forward only (no merge commit), leaving a clean tree."
            ),
            objectives=[
                "Remain on branch `main`.",
                "Local `main` matches the recorded origin tip.",
                "History is a fast-forward (HEAD has a single parent chain).",
                "Working tree is clean and upstream still tracks origin/main.",
            ],
        )

    def setup(self, repo_path: Path) -> TrackingPullState:
        workspace = repo_path.resolve().parent
        remotes_dir = workspace / "remotes"
        bare_path = remotes_dir / "origin.git"
        if bare_path.exists():
            from praxis.workspace import _rmtree

            _rmtree(bare_path)

        local_old_sha = init_configsvc_repo(repo_path)
        git_ops.init_bare(bare_path)
        git_ops.remote_add(repo_path, "origin", str(bare_path))
        git_ops.push(repo_path, "origin", "main", set_upstream=True)

        # Advance origin ahead of local by committing in a temporary clone.
        seed_clone = remotes_dir / "_seed"
        if seed_clone.exists():
            from praxis.workspace import _rmtree

            _rmtree(seed_clone)
        git_ops.clone(str(bare_path), seed_clone)
        git_ops.configure_lab_repo(seed_clone, hooks_path=hooks_path_for_repo(seed_clone))
        write_text(seed_clone, README_MD, REMOTE_README)
        write_text(seed_clone, SETTINGS_TOML, REMOTE_SETTINGS)
        git_ops.add_paths(seed_clone, README_MD, SETTINGS_TOML)
        origin_main_tip_sha = git_ops.commit(
            seed_clone, "Update README and settings from teammates"
        )
        git_ops.push(seed_clone, "origin", "main")

        # Refresh remote-tracking ref without updating local main.
        git_ops.fetch(repo_path, "origin")
        # Leave seed_clone in place on Windows-friendly setups (no forced rmtree).

        state = TrackingPullState(
            local_old_sha=local_old_sha,
            origin_main_tip_sha=origin_main_tip_sha,
            expected_readme=REMOTE_README,
            expected_settings=REMOTE_SETTINGS,
        )
        self._verify_setup(repo_path, state)
        return state

    def _verify_setup(self, repo_path: Path, state: TrackingPullState) -> None:
        errors: list[str] = []
        if git_ops.current_branch(repo_path) != "main":
            errors.append("Expected to be on main")
        if git_ops.rev_parse(repo_path, "HEAD") != state.local_old_sha:
            errors.append("Local HEAD should still be at local_old_sha")
        try:
            remote_tip = git_ops.rev_parse(repo_path, "origin/main")
        except ProcessError as exc:
            errors.append(f"origin/main missing: {exc.message}")
            remote_tip = None
        if remote_tip != state.origin_main_tip_sha:
            errors.append("origin/main does not match recorded tip")
        if not git_ops.is_ancestor(
            repo_path, state.local_old_sha, state.origin_main_tip_sha
        ):
            errors.append("origin tip should be a descendant of local_old_sha")
        upstream = git_ops.branch_upstream(repo_path, "main")
        if upstream != "origin/main":
            errors.append(f"Expected upstream origin/main, got {upstream!r}")
        if errors:
            raise ScenarioSetupError(
                "tracking-pull setup postconditions failed:\n- "
                + "\n- ".join(errors)
            )

    def validate(
        self, repo_path: Path, state: TrackingPullState
    ) -> CheckResult:
        objectives = [
            self._check_on_main(repo_path),
            self._check_matches_origin(repo_path, state),
            self._check_fast_forward(repo_path, state),
            self._check_content(repo_path, state),
            self._check_clean(repo_path),
            self._check_upstream(repo_path),
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

    def _check_matches_origin(
        self, repo_path: Path, state: TrackingPullState
    ) -> ObjectiveResult:
        head = git_ops.rev_parse(repo_path, "HEAD")
        passed = head == state.origin_main_tip_sha
        return ObjectiveResult(
            id="matches-origin",
            description="Local main matches the recorded origin tip",
            passed=passed,
            detail=None
            if passed
            else f"HEAD={head}, expected={state.origin_main_tip_sha}",
        )

    def _check_fast_forward(
        self, repo_path: Path, state: TrackingPullState
    ) -> ObjectiveResult:
        parents = git_ops.commit_parents(repo_path, "HEAD")
        is_ff = git_ops.is_ancestor(
            repo_path, state.local_old_sha, "HEAD"
        ) and len(parents) <= 1
        head = git_ops.rev_parse(repo_path, "HEAD")
        passed = is_ff and head == state.origin_main_tip_sha
        return ObjectiveResult(
            id="fast-forward",
            description="Update is a fast-forward (no merge commit)",
            passed=passed,
            detail=None
            if passed
            else f"parents={parents}, HEAD={head}",
        )

    def _check_content(
        self, repo_path: Path, state: TrackingPullState
    ) -> ObjectiveResult:
        readme = show_file_at(repo_path, "HEAD", README_MD)
        settings = show_file_at(repo_path, "HEAD", SETTINGS_TOML)
        passed = (
            readme == state.expected_readme
            and settings == state.expected_settings
        )
        return ObjectiveResult(
            id="remote-content",
            description="HEAD contains the teammate README and settings updates",
            passed=passed,
            detail=None if passed else "File contents do not match origin tip",
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

    def _check_upstream(self, repo_path: Path) -> ObjectiveResult:
        upstream = git_ops.branch_upstream(repo_path, "main")
        passed = upstream == "origin/main"
        return ObjectiveResult(
            id="upstream",
            description="main still tracks origin/main",
            passed=passed,
            detail=None if passed else f"upstream={upstream!r}",
        )
