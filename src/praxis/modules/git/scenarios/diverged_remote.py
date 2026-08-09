"""Git diverged-remote training scenario."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict

from praxis.errors import ProcessError, ScenarioSetupError
from praxis.models import Assignment, CheckResult, ObjectiveResult
from praxis.modules.git import git_ops
from praxis.modules.git.configsvc import (
    README_MD,
    hooks_path_for_repo,
    init_configsvc_repo,
    show_file_at,
    write_text,
)

LOCAL_README = """\
# configsvc

Tiny settings helper used by Praxis Git labs.

Local-only note on main.
"""

REMOTE_README = """\
# configsvc

Tiny settings helper used by Praxis Git labs.

Remote-only note on origin/main.
"""

COMBINED_README = """\
# configsvc

Tiny settings helper used by Praxis Git labs.

Local-only note on main.
Remote-only note on origin/main.
"""


class DivergedRemoteState(BaseModel):
    model_config = ConfigDict(frozen=True)

    local_old_sha: str
    origin_main_tip_sha: str
    expected_readme: str


class DivergedRemoteScenario:
    """Reconcile diverged local and remote main branches."""

    id: str = "diverged-remote"
    module: str = "git"
    title: str = "Reconcile a diverged local and remote branch"
    description: str = (
        "Local main and origin/main have diverged. Integrate both sides so "
        "history includes each unique commit and README combines both notes."
    )
    difficulty: str | None = "advanced"
    concepts: list[str] = ["diverged-branches", "pull", "rebase", "merge"]
    state_model: type[DivergedRemoteState] = DivergedRemoteState

    def assignment(self) -> Assignment:
        return Assignment(
            title=self.title,
            summary=(
                "Your local `main` and `origin/main` have diverged: each has a "
                "unique README note. Integrate them so `main` contains both "
                "notes (combined README), includes both lines of history "
                "(merge or rebase onto origin is fine), tracks `origin/main`, "
                "and ends clean. Do not drop either side's unique commit."
            ),
            objectives=[
                "Remain on `main` with a clean tree.",
                "README contains both local and remote notes.",
                "History contains both the pre-divergence local commit and "
                "the recorded origin tip (as ancestors or merge parents).",
                "Upstream still tracks origin/main.",
            ],
        )

    def setup(self, repo_path: Path) -> DivergedRemoteState:
        workspace = repo_path.resolve().parent
        remotes_dir = workspace / "remotes"
        bare_path = remotes_dir / "origin.git"
        if bare_path.exists():
            from praxis.workspace import _rmtree

            _rmtree(bare_path)

        base_sha = init_configsvc_repo(repo_path)
        git_ops.init_bare(bare_path)
        git_ops.remote_add(repo_path, "origin", str(bare_path))
        git_ops.push(repo_path, "origin", "main", set_upstream=True)

        # Local unique commit
        write_text(repo_path, README_MD, LOCAL_README)
        git_ops.add_all(repo_path)
        local_old_sha = git_ops.commit(repo_path, "Local README note")

        # Remote unique commit from seed clone based on base
        seed = remotes_dir / "_seed"
        if seed.exists():
            from praxis.workspace import _rmtree

            _rmtree(seed)
        git_ops.clone(str(bare_path), seed)
        git_ops.configure_lab_repo(seed, hooks_path=hooks_path_for_repo(seed))
        # Reset seed to base then commit remote note (bare still at base)
        git_ops.reset(seed, base_sha, mode="hard")
        write_text(seed, README_MD, REMOTE_README)
        git_ops.add_paths(seed, README_MD)
        origin_main_tip_sha = git_ops.commit(seed, "Remote README note")
        git_ops.push(seed, "origin", "main")
        # Keep seed directory (avoid Windows rmtree locks on active git dirs).

        git_ops.fetch(repo_path, "origin")

        state = DivergedRemoteState(
            local_old_sha=local_old_sha,
            origin_main_tip_sha=origin_main_tip_sha,
            expected_readme=COMBINED_README,
        )
        self._verify_setup(repo_path, state)
        return state

    def _verify_setup(self, repo_path: Path, state: DivergedRemoteState) -> None:
        errors: list[str] = []
        if git_ops.rev_parse(repo_path, "HEAD") != state.local_old_sha:
            errors.append("local HEAD mismatch")
        try:
            remote = git_ops.rev_parse(repo_path, "origin/main")
        except ProcessError as exc:
            errors.append(str(exc.message))
            remote = None
        if remote != state.origin_main_tip_sha:
            errors.append("origin/main mismatch")
        if git_ops.is_ancestor(repo_path, state.local_old_sha, "origin/main"):
            errors.append("branches should have diverged")
        if git_ops.is_ancestor(repo_path, state.origin_main_tip_sha, "HEAD"):
            errors.append("local should not already contain origin tip")
        if errors:
            raise ScenarioSetupError(
                "diverged-remote setup postconditions failed:\n- "
                + "\n- ".join(errors)
            )

    def validate(self, repo_path: Path, state: DivergedRemoteState) -> CheckResult:
        objectives = [
            self._on_main(repo_path),
            self._readme(repo_path, state),
            self._contains_both(repo_path, state),
            self._upstream(repo_path),
            self._clean(repo_path),
        ]
        return CheckResult(
            passed=all(o.passed for o in objectives), objectives=objectives
        )

    def _on_main(self, repo_path: Path) -> ObjectiveResult:
        if git_ops.is_detached_head(repo_path):
            return ObjectiveResult(
                id="on-main",
                description="On main",
                passed=False,
                detail="detached",
            )
        branch = git_ops.current_branch(repo_path)
        return ObjectiveResult(
            id="on-main",
            description="On main",
            passed=branch == "main",
            detail=None if branch == "main" else branch,
        )

    def _readme(
        self, repo_path: Path, state: DivergedRemoteState
    ) -> ObjectiveResult:
        actual = show_file_at(repo_path, "HEAD", README_MD)
        # Accept exact combined or both phrases present
        if actual is None:
            passed = False
        else:
            passed = (
                actual == state.expected_readme
                or (
                    "Local-only note" in actual and "Remote-only note" in actual
                )
            )
        return ObjectiveResult(
            id="combined-readme",
            description="README includes both local and remote notes",
            passed=passed,
            detail=None if passed else "README missing one side",
        )

    def _contains_both(
        self, repo_path: Path, state: DivergedRemoteState
    ) -> ObjectiveResult:
        has_local = git_ops.is_ancestor(repo_path, state.local_old_sha, "HEAD")
        has_remote = git_ops.is_ancestor(
            repo_path, state.origin_main_tip_sha, "HEAD"
        )
        passed = has_local and has_remote
        return ObjectiveResult(
            id="both-histories",
            description="HEAD history includes both diverged tips",
            passed=passed,
            detail=None
            if passed
            else f"local_ancestor={has_local}, remote_ancestor={has_remote}",
        )

    def _upstream(self, repo_path: Path) -> ObjectiveResult:
        upstream = git_ops.branch_upstream(repo_path, "main")
        passed = upstream == "origin/main"
        return ObjectiveResult(
            id="upstream",
            description="main tracks origin/main",
            passed=passed,
            detail=None if passed else repr(upstream),
        )

    def _clean(self, repo_path: Path) -> ObjectiveResult:
        passed = (
            git_ops.is_clean(repo_path)
            and not git_ops.merge_head_exists(repo_path)
            and not git_ops.rebase_in_progress(repo_path)
        )
        return ObjectiveResult(
            id="clean-tree",
            description="Clean tree with no merge/rebase in progress",
            passed=passed,
            detail=None if passed else git_ops.status_porcelain(repo_path),
        )
