"""Git bisect-regression training scenario."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict

from praxis.errors import ScenarioSetupError
from praxis.models import Assignment, CheckResult, ObjectiveResult
from praxis.modules.git import git_ops
from praxis.modules.git.configsvc import (
    APP_PY,
    BASE_APP_PY,
    init_configsvc_repo,
    write_text,
)

ANSWER_FILE = "answer.txt"
VERIFY_SCRIPT = "scripts/verify.sh"

BAD_SENTINEL = "PARSE_BUG = True"


def _app_with_marker(marker: str) -> str:
    return BASE_APP_PY.replace(
        "DEFAULT_TIMEOUT_MS = 1000",
        f"DEFAULT_TIMEOUT_MS = 1000\n{marker}",
    )


GOOD_APP = BASE_APP_PY
BAD_APP = _app_with_marker(BAD_SENTINEL)

VERIFY_SH = """\
#!/usr/bin/env bash
set -euo pipefail
if grep -q 'PARSE_BUG = True' app.py; then
  exit 1
fi
exit 0
"""


class BisectRegressionState(BaseModel):
    model_config = ConfigDict(frozen=True)

    good_sha: str
    first_bad_sha: str
    bad_tip_sha: str


class BisectRegressionScenario:
    """Locate the first bad commit and record its SHA in answer.txt."""

    id: str = "bisect-regression"
    module: str = "git"
    title: str = "Find the commit that introduced a bug"
    description: str = (
        "A regression landed somewhere between a known-good commit and HEAD. "
        "Identify the first bad commit and write its SHA to answer.txt."
    )
    difficulty: str | None = "advanced"
    concepts: list[str] = ["bisect", "diagnosis", "history"]
    state_model: type[BisectRegressionState] = BisectRegressionState

    def assignment(self) -> Assignment:
        return Assignment(
            title=self.title,
            summary=(
                "`app.py` gained a parse regression (`PARSE_BUG = True`) between "
                "a known-good commit and the current tip. A helper script at "
                "`scripts/verify.sh` exits 0 when the bug is absent and 1 when "
                "present. Find the first bad commit and write its full SHA to "
                f"`{ANSWER_FILE}`. Finish with bisect reset (no active bisect) "
                "and a clean tree aside from that answer file."
            ),
            objectives=[
                f"Write the first bad commit SHA to `{ANSWER_FILE}`.",
                "Do not leave an active bisect session.",
                "Working tree is otherwise clean (answer.txt may be untracked "
                "or committed).",
            ],
        )

    def setup(self, repo_path: Path) -> BisectRegressionState:
        good_sha = init_configsvc_repo(repo_path)
        # A few good commits after the initial tip.
        for i in range(1, 4):
            write_text(repo_path, f"notes/good_{i}.txt", f"good note {i}\n")
            git_ops.add_all(repo_path)
            good_sha = git_ops.commit(repo_path, f"Good change {i}")

        write_text(repo_path, APP_PY, BAD_APP)
        git_ops.add_all(repo_path)
        first_bad_sha = git_ops.commit(repo_path, "Refactor settings loader")

        for i in range(1, 4):
            write_text(repo_path, f"notes/after_{i}.txt", f"after bad {i}\n")
            git_ops.add_all(repo_path)
            bad_tip_sha = git_ops.commit(repo_path, f"Follow-up {i}")

        write_text(repo_path, VERIFY_SCRIPT, VERIFY_SH)
        git_ops.add_all(repo_path)
        bad_tip_sha = git_ops.commit(repo_path, "Add verify script for bisect")

        # Leave verify script committed; ensure HEAD is bad tip.
        state = BisectRegressionState(
            good_sha=good_sha,
            first_bad_sha=first_bad_sha,
            bad_tip_sha=bad_tip_sha,
        )
        self._verify_setup(repo_path, state)
        return state

    def _verify_setup(
        self, repo_path: Path, state: BisectRegressionState
    ) -> None:
        errors: list[str] = []
        if git_ops.rev_parse(repo_path, "HEAD") != state.bad_tip_sha:
            errors.append("HEAD should be bad tip")
        if not git_ops.is_ancestor(repo_path, state.good_sha, state.first_bad_sha):
            errors.append("good_sha should be ancestor of first_bad_sha")
        if not git_ops.is_ancestor(
            repo_path, state.first_bad_sha, state.bad_tip_sha
        ):
            errors.append("first_bad_sha should be ancestor of tip")
        app_at_bad = git_ops.show(repo_path, f"{state.first_bad_sha}:{APP_PY}")
        if BAD_SENTINEL not in app_at_bad:
            errors.append("first bad commit lacks sentinel")
        parent = git_ops.commit_parents(repo_path, state.first_bad_sha)[0]
        app_before = git_ops.show(repo_path, f"{parent}:{APP_PY}")
        if BAD_SENTINEL in app_before:
            errors.append("parent of first bad already has sentinel")
        if (repo_path / ".git" / "BISECT_LOG").exists():
            errors.append("bisect must not be active after setup")
        if errors:
            raise ScenarioSetupError(
                "bisect-regression setup postconditions failed:\n- "
                + "\n- ".join(errors)
            )

    def validate(
        self, repo_path: Path, state: BisectRegressionState
    ) -> CheckResult:
        objectives = [
            self._check_answer(repo_path, state),
            self._check_no_bisect(repo_path),
            self._check_clean_enough(repo_path),
        ]
        return CheckResult(
            passed=all(item.passed for item in objectives),
            objectives=objectives,
        )

    def _check_answer(
        self, repo_path: Path, state: BisectRegressionState
    ) -> ObjectiveResult:
        path = repo_path / ANSWER_FILE
        if not path.is_file():
            return ObjectiveResult(
                id="answer-file",
                description=f"{ANSWER_FILE} contains the first bad commit SHA",
                passed=False,
                detail=f"{ANSWER_FILE} is missing",
            )
        raw = path.read_text(encoding="utf-8").strip().split()
        if not raw:
            return ObjectiveResult(
                id="answer-file",
                description=f"{ANSWER_FILE} contains the first bad commit SHA",
                passed=False,
                detail="answer.txt is empty",
            )
        answer = raw[0]
        return ObjectiveResult(
            id="answer-file",
            description=f"{ANSWER_FILE} contains the first bad commit SHA",
            passed=answer == state.first_bad_sha,
            detail=None
            if answer == state.first_bad_sha
            else f"got {answer!r}, expected {state.first_bad_sha}",
        )

    def _check_no_bisect(self, repo_path: Path) -> ObjectiveResult:
        git_dir = Path(git_ops.rev_parse(repo_path, "--git-dir"))
        if not git_dir.is_absolute():
            git_dir = repo_path / git_dir
        active = (git_dir / "BISECT_LOG").exists() or (
            git_dir / "BISECT_START"
        ).exists()
        passed = not active
        return ObjectiveResult(
            id="no-bisect",
            description="No active bisect session",
            passed=passed,
            detail=None if passed else "Bisect appears to still be active",
        )

    def _check_clean_enough(self, repo_path: Path) -> ObjectiveResult:
        status = git_ops.status_porcelain(repo_path)
        lines = [line for line in status.splitlines() if line.strip()]
        allowed = True
        for line in lines:
            path = line[3:].strip() if len(line) > 3 else line
            # Allow answer.txt only
            if path not in {ANSWER_FILE, f"./{ANSWER_FILE}"}:
                # also allow "?? answer.txt"
                if ANSWER_FILE not in path:
                    allowed = False
                    break
        return ObjectiveResult(
            id="clean-enough",
            description="Only answer.txt may be dirty/untracked",
            passed=allowed,
            detail=None if allowed else f"Unexpected dirty paths:\n{status.rstrip()}",
        )
