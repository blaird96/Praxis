"""Git selective-stage training scenario."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict

from praxis.errors import ScenarioSetupError
from praxis.models import Assignment, CheckResult, ObjectiveResult
from praxis.modules.git import git_ops
from praxis.modules.git.configsvc import (
    APP_PY,
    BASE_APP_PY,
    SETTINGS_TOML,
    init_configsvc_repo,
    show_file_at,
    write_text,
)

NOTES_SCRATCH = "notes.scratch"

FIXED_APP_PY = BASE_APP_PY.replace(
    "DEFAULT_TIMEOUT_MS = 1000",
    "DEFAULT_TIMEOUT_MS = 1500",
)

DIRTY_SETTINGS = """\
# configsvc settings
timeout_ms = 9999
log_level = "debug"
# accidental local tweak - do not commit
"""

SCRATCH_CONTENT = "scratch notes - do not commit\n"


class SelectiveStageState(BaseModel):
    """Immutable facts recorded when selective-stage setup completes."""

    model_config = ConfigDict(frozen=True)

    base_sha: str
    expected_app: str
    forbidden_settings: str
    forbidden_notes: str


class SelectiveStageScenario:
    """Commit only the intended app.py fix; leave other dirt unstaged."""

    id: str = "selective-stage"
    module: str = "git"
    title: str = "Stage only the intended changes"
    description: str = (
        "Commit a real bugfix in app.py without staging scratch notes or "
        "an accidental settings edit."
    )
    difficulty: str | None = "beginner"
    concepts: list[str] = ["staging", "index", "path-limited-add"]
    state_model: type[SelectiveStageState] = SelectiveStageState

    def assignment(self) -> Assignment:
        return Assignment(
            title=self.title,
            summary=(
                "You fixed a real bug in `app.py` (default timeout should be "
                "1500). You also have an accidental `settings.toml` tweak and "
                "a `notes.scratch` file that must not be committed. Create one "
                "commit that contains only the `app.py` fix; leave the other "
                "dirty files unstaged in the working tree."
            ),
            objectives=[
                "Create exactly one new commit on the current branch.",
                "HEAD's app.py matches the fixed content.",
                "HEAD must not include the dirty settings.toml or notes.scratch.",
                "settings.toml and notes.scratch remain dirty/untracked after "
                "the commit.",
            ],
        )

    def setup(self, repo_path: Path) -> SelectiveStageState:
        base_sha = init_configsvc_repo(repo_path)
        write_text(repo_path, APP_PY, FIXED_APP_PY)
        write_text(repo_path, SETTINGS_TOML, DIRTY_SETTINGS)
        write_text(repo_path, NOTES_SCRATCH, SCRATCH_CONTENT)
        state = SelectiveStageState(
            base_sha=base_sha,
            expected_app=FIXED_APP_PY,
            forbidden_settings=DIRTY_SETTINGS,
            forbidden_notes=SCRATCH_CONTENT,
        )
        self._verify_setup(repo_path, state)
        return state

    def _verify_setup(self, repo_path: Path, state: SelectiveStageState) -> None:
        errors: list[str] = []
        if git_ops.rev_parse(repo_path, "HEAD") != state.base_sha:
            errors.append("HEAD does not match base_sha")
        if git_ops.is_clean(repo_path):
            errors.append("Expected dirty working tree after setup")
        status = git_ops.status_porcelain(repo_path)
        for needle in (APP_PY, SETTINGS_TOML, NOTES_SCRATCH):
            if needle not in status:
                errors.append(f"Expected {needle} to appear in status")
        if errors:
            raise ScenarioSetupError(
                "selective-stage setup postconditions failed:\n- "
                + "\n- ".join(errors)
            )

    def validate(
        self, repo_path: Path, state: SelectiveStageState
    ) -> CheckResult:
        objectives = [
            self._check_one_commit(repo_path, state),
            self._check_app_committed(repo_path, state),
            self._check_settings_not_committed(repo_path, state),
            self._check_notes_not_committed(repo_path, state),
            self._check_dirt_remains(repo_path),
        ]
        return CheckResult(
            passed=all(item.passed for item in objectives),
            objectives=objectives,
        )

    def _check_one_commit(
        self, repo_path: Path, state: SelectiveStageState
    ) -> ObjectiveResult:
        head = git_ops.rev_parse(repo_path, "HEAD")
        parents = git_ops.commit_parents(repo_path, "HEAD")
        passed = head != state.base_sha and parents == [state.base_sha]
        return ObjectiveResult(
            id="one-commit",
            description="Exactly one new commit on top of the setup tip",
            passed=passed,
            detail=None
            if passed
            else f"HEAD={head}, parents={parents}, base={state.base_sha}",
        )

    def _check_app_committed(
        self, repo_path: Path, state: SelectiveStageState
    ) -> ObjectiveResult:
        actual = show_file_at(repo_path, "HEAD", APP_PY)
        passed = actual == state.expected_app
        return ObjectiveResult(
            id="app-committed",
            description="HEAD includes the fixed app.py",
            passed=passed,
            detail=None if passed else "app.py at HEAD does not match the fix",
        )

    def _check_settings_not_committed(
        self, repo_path: Path, state: SelectiveStageState
    ) -> ObjectiveResult:
        actual = show_file_at(repo_path, "HEAD", SETTINGS_TOML)
        passed = actual is not None and actual != state.forbidden_settings
        return ObjectiveResult(
            id="settings-excluded",
            description="HEAD does not include the dirty settings.toml",
            passed=passed,
            detail=None if passed else "Dirty settings.toml was committed",
        )

    def _check_notes_not_committed(
        self, repo_path: Path, state: SelectiveStageState
    ) -> ObjectiveResult:
        actual = show_file_at(repo_path, "HEAD", NOTES_SCRATCH)
        passed = actual is None
        return ObjectiveResult(
            id="notes-excluded",
            description="notes.scratch is not present in HEAD",
            passed=passed,
            detail=None if passed else "notes.scratch was committed",
        )

    def _check_dirt_remains(self, repo_path: Path) -> ObjectiveResult:
        status = git_ops.status_porcelain(repo_path)
        has_settings = SETTINGS_TOML in status
        has_notes = NOTES_SCRATCH in status
        passed = has_settings and has_notes
        detail = None
        if not passed:
            missing = []
            if not has_settings:
                missing.append(SETTINGS_TOML)
            if not has_notes:
                missing.append(NOTES_SCRATCH)
            detail = (
                "Expected remaining dirty/untracked files: "
                + ", ".join(missing)
            )
        return ObjectiveResult(
            id="dirt-remains",
            description="Excluded dirty files remain in the working tree",
            passed=passed,
            detail=detail,
        )
