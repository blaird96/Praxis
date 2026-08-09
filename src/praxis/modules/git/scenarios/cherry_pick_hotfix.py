"""Git cherry-pick-hotfix training scenario."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict

from praxis.errors import ScenarioSetupError
from praxis.models import Assignment, CheckResult, ObjectiveResult
from praxis.modules.git import git_ops
from praxis.modules.git.configsvc import (
    APP_PY,
    README_MD,
    init_configsvc_repo,
    show_file_at,
    write_text,
)

HOTFIX_BRANCH = "hotfix/timeout"
RELEASE_BRANCH = "release/1.0"

HOTFIX_APP = '''\
"""Minimal settings service for Praxis labs."""

from pathlib import Path

DEFAULT_TIMEOUT_MS = 2000


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
'''

HOTFIX_ONLY_README = """\
# configsvc

Tiny settings helper used by Praxis Git labs.

Hotfix branch notes - do not bring this file change to release.
"""


class CherryPickHotfixState(BaseModel):
    model_config = ConfigDict(frozen=True)

    release_tip_sha: str
    hotfix_commit_sha: str
    expected_app: str
    release_readme: str


class CherryPickHotfixScenario:
    """Cherry-pick a single hotfix commit onto a release branch."""

    id: str = "cherry-pick-hotfix"
    module: str = "git"
    title: str = "Cherry-pick a hotfix onto another branch"
    description: str = (
        "Bring only the timeout fix commit onto release/1.0 without merging "
        "the whole hotfix branch."
    )
    difficulty: str | None = "intermediate"
    concepts: list[str] = ["cherry-pick"]
    state_model: type[CherryPickHotfixState] = CherryPickHotfixState

    def assignment(self) -> Assignment:
        return Assignment(
            title=self.title,
            summary=(
                f"Branch `{HOTFIX_BRANCH}` contains a good timeout fix commit "
                "and a later README-only commit you must not bring over. "
                f"Apply only the timeout fix onto `{RELEASE_BRANCH}`, leave a "
                "linear tip (not a merge of the whole branch), and keep the "
                "release README unchanged."
            ),
            objectives=[
                f"Remain on `{RELEASE_BRANCH}`.",
                "HEAD includes the timeout app.py fix.",
                "HEAD README still matches the pre-pick release README.",
                "HEAD is not a merge commit of the hotfix branch tip.",
            ],
        )

    def setup(self, repo_path: Path) -> CherryPickHotfixState:
        init_configsvc_repo(repo_path)
        git_ops.create_branch(repo_path, RELEASE_BRANCH)
        release_tip_sha = git_ops.rev_parse(repo_path, "HEAD")
        release_readme = git_ops.show(repo_path, f"HEAD:{README_MD}").replace(
            "\r\n", "\n"
        )

        git_ops.switch_branch(repo_path, HOTFIX_BRANCH, create=True)
        write_text(repo_path, APP_PY, HOTFIX_APP)
        git_ops.add_all(repo_path)
        hotfix_commit_sha = git_ops.commit(repo_path, "Fix default timeout")
        write_text(repo_path, README_MD, HOTFIX_ONLY_README)
        git_ops.add_all(repo_path)
        git_ops.commit(repo_path, "Hotfix branch notes")

        git_ops.checkout(repo_path, RELEASE_BRANCH)
        state = CherryPickHotfixState(
            release_tip_sha=release_tip_sha,
            hotfix_commit_sha=hotfix_commit_sha,
            expected_app=HOTFIX_APP,
            release_readme=release_readme,
        )
        self._verify_setup(repo_path, state)
        return state

    def _verify_setup(
        self, repo_path: Path, state: CherryPickHotfixState
    ) -> None:
        errors: list[str] = []
        if git_ops.current_branch(repo_path) != RELEASE_BRANCH:
            errors.append("expected release branch")
        if git_ops.rev_parse(repo_path, "HEAD") != state.release_tip_sha:
            errors.append("release tip mismatch")
        if errors:
            raise ScenarioSetupError(
                "cherry-pick-hotfix setup postconditions failed:\n- "
                + "\n- ".join(errors)
            )

    def validate(
        self, repo_path: Path, state: CherryPickHotfixState
    ) -> CheckResult:
        objectives = [
            self._on_release(repo_path),
            self._app(repo_path, state),
            self._readme(repo_path, state),
            self._not_full_merge(repo_path, state),
            self._clean(repo_path),
        ]
        return CheckResult(
            passed=all(o.passed for o in objectives), objectives=objectives
        )

    def _on_release(self, repo_path: Path) -> ObjectiveResult:
        if git_ops.is_detached_head(repo_path):
            return ObjectiveResult(
                id="on-release",
                description=f"On {RELEASE_BRANCH}",
                passed=False,
                detail="detached",
            )
        branch = git_ops.current_branch(repo_path)
        return ObjectiveResult(
            id="on-release",
            description=f"On {RELEASE_BRANCH}",
            passed=branch == RELEASE_BRANCH,
            detail=None if branch == RELEASE_BRANCH else branch,
        )

    def _app(
        self, repo_path: Path, state: CherryPickHotfixState
    ) -> ObjectiveResult:
        actual = show_file_at(repo_path, "HEAD", APP_PY)
        passed = actual == state.expected_app
        return ObjectiveResult(
            id="app-fix",
            description="app.py includes the timeout fix",
            passed=passed,
            detail=None if passed else "app.py mismatch",
        )

    def _readme(
        self, repo_path: Path, state: CherryPickHotfixState
    ) -> ObjectiveResult:
        actual = show_file_at(repo_path, "HEAD", README_MD)
        passed = actual == state.release_readme
        return ObjectiveResult(
            id="readme-unchanged",
            description="release README was not replaced by hotfix notes",
            passed=passed,
            detail=None if passed else "README changed unexpectedly",
        )

    def _not_full_merge(
        self, repo_path: Path, state: CherryPickHotfixState
    ) -> ObjectiveResult:
        parents = git_ops.commit_parents(repo_path, "HEAD")
        hotfix_tip = git_ops.rev_parse(repo_path, HOTFIX_BRANCH)
        # Reject merging the whole hotfix branch tip as second parent
        passed = len(parents) == 1 and hotfix_tip not in parents
        return ObjectiveResult(
            id="cherry-pick-not-merge",
            description="Applied as cherry-pick/linear commit, not full branch merge",
            passed=passed,
            detail=None if passed else f"parents={parents}",
        )

    def _clean(self, repo_path: Path) -> ObjectiveResult:
        passed = git_ops.is_clean(repo_path)
        return ObjectiveResult(
            id="clean-tree",
            description="Working tree is clean",
            passed=passed,
            detail=None if passed else git_ops.status_porcelain(repo_path),
        )
