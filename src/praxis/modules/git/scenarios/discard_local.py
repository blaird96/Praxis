"""Git discard-local training scenario."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict

from praxis.errors import ScenarioSetupError
from praxis.models import Assignment, CheckResult, ObjectiveResult
from praxis.modules.git import git_ops
from praxis.modules.git.configsvc import (
    APP_PY,
    BASE_APP_PY,
    README_MD,
    SETTINGS_TOML,
    init_configsvc_repo,
    read_text_normalized,
    write_text,
)

KEEP_README = """\
# configsvc

Tiny settings helper used by Praxis Git labs.

Keep this README edit.
"""

BAD_APP = BASE_APP_PY.replace("DEFAULT_TIMEOUT_MS = 1000", "DEFAULT_TIMEOUT_MS = 1")
BAD_SETTINGS = """\
# configsvc settings
timeout_ms = 1
log_level = "trace"
"""


class DiscardLocalState(BaseModel):
    model_config = ConfigDict(frozen=True)

    base_sha: str
    expected_app: str
    expected_settings: str
    expected_readme: str


class DiscardLocalScenario:
    """Discard unwanted local edits while keeping an intentional README change."""

    id: str = "discard-local"
    module: str = "git"
    title: str = "Discard the wrong uncommitted edits"
    description: str = (
        "Throw away accidental app.py and settings.toml edits while keeping a "
        "README change you still want."
    )
    difficulty: str | None = "beginner"
    concepts: list[str] = ["restore", "discard", "working-tree"]
    state_model: type[DiscardLocalState] = DiscardLocalState

    def assignment(self) -> Assignment:
        return Assignment(
            title=self.title,
            summary=(
                "You have three uncommitted edits. Keep the README.md change, "
                "but discard the accidental `app.py` and `settings.toml` edits "
                "so those two files match HEAD again. You may leave the README "
                "dirty or commit it; discarded files must match HEAD."
            ),
            objectives=[
                "app.py matches HEAD (bad edit discarded).",
                "settings.toml matches HEAD (bad edit discarded).",
                "README.md still contains your keep-me edit (dirty or committed).",
            ],
        )

    def setup(self, repo_path: Path) -> DiscardLocalState:
        base_sha = init_configsvc_repo(repo_path)
        write_text(repo_path, APP_PY, BAD_APP)
        write_text(repo_path, SETTINGS_TOML, BAD_SETTINGS)
        write_text(repo_path, README_MD, KEEP_README)
        state = DiscardLocalState(
            base_sha=base_sha,
            expected_app=BASE_APP_PY,
            expected_settings=git_ops.show(repo_path, f"{base_sha}:{SETTINGS_TOML}"),
            expected_readme=KEEP_README,
        )
        # Normalize expected settings newlines
        state = DiscardLocalState(
            base_sha=base_sha,
            expected_app=BASE_APP_PY,
            expected_settings=state.expected_settings.replace("\r\n", "\n"),
            expected_readme=KEEP_README,
        )
        self._verify_setup(repo_path, state)
        return state

    def _verify_setup(self, repo_path: Path, state: DiscardLocalState) -> None:
        errors: list[str] = []
        if git_ops.is_clean(repo_path):
            errors.append("Expected dirty tree")
        if read_text_normalized(repo_path, README_MD) != state.expected_readme:
            errors.append("README keep content missing")
        if errors:
            raise ScenarioSetupError(
                "discard-local setup postconditions failed:\n- "
                + "\n- ".join(errors)
            )

    def validate(self, repo_path: Path, state: DiscardLocalState) -> CheckResult:
        objectives = [
            self._file_matches_head(repo_path, APP_PY, "app-restored"),
            self._file_matches_head(repo_path, SETTINGS_TOML, "settings-restored"),
            self._readme_kept(repo_path, state),
        ]
        return CheckResult(
            passed=all(o.passed for o in objectives), objectives=objectives
        )

    def _file_matches_head(
        self, repo_path: Path, relative: str, objective_id: str
    ) -> ObjectiveResult:
        worktree = read_text_normalized(repo_path, relative)
        head = git_ops.show(repo_path, f"HEAD:{relative}").replace("\r\n", "\n")
        passed = worktree == head
        return ObjectiveResult(
            id=objective_id,
            description=f"{relative} matches HEAD",
            passed=passed,
            detail=None if passed else f"{relative} still differs from HEAD",
        )

    def _readme_kept(
        self, repo_path: Path, state: DiscardLocalState
    ) -> ObjectiveResult:
        # Accept worktree or HEAD containing expected readme
        worktree = read_text_normalized(repo_path, README_MD)
        head = git_ops.show(repo_path, f"HEAD:{README_MD}").replace("\r\n", "\n")
        passed = (
            worktree == state.expected_readme or head == state.expected_readme
        )
        return ObjectiveResult(
            id="readme-kept",
            description="README keep-me edit is still present",
            passed=passed,
            detail=None if passed else "README keep edit was lost",
        )
