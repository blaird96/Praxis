"""Git stash-context-switch training scenario."""

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
    read_text_normalized,
    show_file_at,
    write_text,
)

FEATURE_BRANCH = "feature/logs"

WIP_APP = '''\
"""Minimal settings service for Praxis labs."""

from pathlib import Path

DEFAULT_TIMEOUT_MS = 1000
# WIP: structured logging hook
LOG_FORMAT = "json"


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

FIXED_README = """\
# configsvc

Tiny settings helper used by Praxis Git labs.

Hotfix: document the support contact as ops@example.invalid.
"""


class StashContextSwitchState(BaseModel):
    model_config = ConfigDict(frozen=True)

    main_tip_sha: str
    feature_tip_sha: str
    wip_app: str
    expected_readme: str


class StashContextSwitchScenario:
    """Park WIP, commit an urgent main fix, restore WIP on the feature branch."""

    id: str = "stash-context-switch"
    module: str = "git"
    title: str = "Park WIP and switch branches cleanly"
    description: str = (
        "You have uncommitted work on a feature branch when an urgent README "
        "fix is needed on main. Park the WIP, ship the fix, then restore it."
    )
    difficulty: str | None = "intermediate"
    concepts: list[str] = ["stash", "branch-switch", "working-tree"]
    state_model: type[StashContextSwitchState] = StashContextSwitchState

    def assignment(self) -> Assignment:
        return Assignment(
            title=self.title,
            summary=(
                f"You are mid-edit on `{FEATURE_BRANCH}` with uncommitted "
                "logging WIP in `app.py`. An urgent README hotfix must land on "
                "`main` (add the support contact line). Park your WIP, commit "
                "the README fix on `main`, then return to the feature branch "
                "with the original WIP restored. Do not commit the WIP onto "
                "`main`."
            ),
            objectives=[
                "Commit the README hotfix on `main` (main moves one commit).",
                f"End on `{FEATURE_BRANCH}` with the WIP `app.py` content restored.",
                "Do not leave the WIP committed on `main`.",
                "No merge/rebase in progress.",
            ],
        )

    def setup(self, repo_path: Path) -> StashContextSwitchState:
        main_tip_sha = init_configsvc_repo(repo_path)
        git_ops.switch_branch(repo_path, FEATURE_BRANCH, create=True)
        write_text(
            repo_path,
            "logs.md",
            "# Logging notes\n\nFeature branch marker.\n",
        )
        git_ops.add_all(repo_path)
        feature_tip_sha = git_ops.commit(repo_path, "Start logging feature")
        write_text(repo_path, APP_PY, WIP_APP)

        state = StashContextSwitchState(
            main_tip_sha=main_tip_sha,
            feature_tip_sha=feature_tip_sha,
            wip_app=WIP_APP,
            expected_readme=FIXED_README,
        )
        self._verify_setup(repo_path, state)
        return state

    def _verify_setup(
        self, repo_path: Path, state: StashContextSwitchState
    ) -> None:
        errors: list[str] = []
        if git_ops.current_branch(repo_path) != FEATURE_BRANCH:
            errors.append(f"Expected {FEATURE_BRANCH}")
        if git_ops.rev_parse(repo_path, "main") != state.main_tip_sha:
            errors.append("main tip mismatch")
        if git_ops.rev_parse(repo_path, "HEAD") != state.feature_tip_sha:
            errors.append("feature tip mismatch")
        if git_ops.is_clean(repo_path):
            errors.append("Expected dirty WIP on feature")
        if read_text_normalized(repo_path, APP_PY) != state.wip_app:
            errors.append("WIP app.py content mismatch")
        if errors:
            raise ScenarioSetupError(
                "stash-context-switch setup postconditions failed:\n- "
                + "\n- ".join(errors)
            )

    def validate(
        self, repo_path: Path, state: StashContextSwitchState
    ) -> CheckResult:
        objectives = [
            self._check_on_feature(repo_path),
            self._check_main_hotfix(repo_path, state),
            self._check_wip_not_on_main(repo_path, state),
            self._check_wip_restored(repo_path, state),
            self._check_feature_tip(repo_path, state),
            self._check_no_integration(repo_path),
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

    def _check_main_hotfix(
        self, repo_path: Path, state: StashContextSwitchState
    ) -> ObjectiveResult:
        main_sha = git_ops.rev_parse(repo_path, "main")
        parents = git_ops.commit_parents(repo_path, "main")
        readme = show_file_at(repo_path, "main", README_MD)
        passed = (
            main_sha != state.main_tip_sha
            and parents == [state.main_tip_sha]
            and readme == state.expected_readme
        )
        return ObjectiveResult(
            id="main-hotfix",
            description="main has exactly one README hotfix commit",
            passed=passed,
            detail=None
            if passed
            else f"main={main_sha}, parents={parents}",
        )

    def _check_wip_not_on_main(
        self, repo_path: Path, state: StashContextSwitchState
    ) -> ObjectiveResult:
        app_on_main = show_file_at(repo_path, "main", APP_PY)
        passed = app_on_main != state.wip_app
        return ObjectiveResult(
            id="wip-not-on-main",
            description="WIP app.py was not committed onto main",
            passed=passed,
            detail=None if passed else "main contains the WIP app.py content",
        )

    def _check_wip_restored(
        self, repo_path: Path, state: StashContextSwitchState
    ) -> ObjectiveResult:
        if not (repo_path / APP_PY).is_file():
            return ObjectiveResult(
                id="wip-restored",
                description="WIP app.py content is restored in the worktree",
                passed=False,
                detail="app.py missing",
            )
        actual = read_text_normalized(repo_path, APP_PY)
        passed = actual == state.wip_app
        return ObjectiveResult(
            id="wip-restored",
            description="WIP app.py content is restored in the worktree",
            passed=passed,
            detail=None if passed else "Worktree app.py does not match WIP",
        )

    def _check_feature_tip(
        self, repo_path: Path, state: StashContextSwitchState
    ) -> ObjectiveResult:
        tip = git_ops.rev_parse(repo_path, FEATURE_BRANCH)
        # Feature tip may stay put (stash) or move if learner committed WIP;
        # require no WIP committed on feature either — tip should remain setup tip
        # OR worktree has WIP and HEAD tip equals feature_tip_sha.
        passed = tip == state.feature_tip_sha
        return ObjectiveResult(
            id="feature-tip",
            description="Feature branch tip was not used to store the WIP commit",
            passed=passed,
            detail=None
            if passed
            else f"{FEATURE_BRANCH}={tip}, expected={state.feature_tip_sha}",
        )

    def _check_no_integration(self, repo_path: Path) -> ObjectiveResult:
        passed = (
            not git_ops.merge_head_exists(repo_path)
            and not git_ops.rebase_in_progress(repo_path)
        )
        return ObjectiveResult(
            id="no-integration",
            description="No merge or rebase is in progress",
            passed=passed,
            detail=None if passed else "Merge or rebase still in progress",
        )
