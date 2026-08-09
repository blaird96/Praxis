"""Git merge-conflict training scenario."""

from __future__ import annotations

import re
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from praxis.errors import ProcessError, ScenarioSetupError
from praxis.models import Assignment, CheckResult, ObjectiveResult
from praxis.modules.git import git_ops

GREETING_FILE = "greeting.txt"

BASE_CONTENT = "Hello from main\nShared line\n"
MAIN_CONTENT = "Hello from main branch\nShared line\n"
FEATURE_CONTENT = "Hello from feature branch\nShared line\n"
EXPECTED_RESOLVED_CONTENT = (
    "Hello from main branch\nHello from feature branch\nShared line\n"
)

# Match standard conflict marker lines (optional label after the marker).
_CONFLICT_MARKER_LINE = re.compile(
    r"^(<<<<<<<|=======|>>>>>>>)( .*)?$",
    re.MULTILINE,
)


class MergeConflictState(BaseModel):
    """Immutable facts recorded when merge-conflict setup completes."""

    model_config = ConfigDict(frozen=True)

    base_sha: str
    main_tip_sha: str
    feature_tip_sha: str


def _hooks_path_for_repo(repo_path: Path) -> Path:
    """Praxis-controlled hooks dir: sibling ``.praxis/hooks`` outside the repo."""
    return repo_path.resolve().parent / ".praxis" / "hooks"


def _write_text(repo_path: Path, relative: str, content: str) -> None:
    path = repo_path / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content.encode("utf-8"))


def _read_text_normalized(repo_path: Path, relative: str) -> str:
    raw = (repo_path / relative).read_bytes().decode("utf-8")
    return raw.replace("\r\n", "\n").replace("\r", "\n")


def _contains_conflict_markers(text: str) -> bool:
    return _CONFLICT_MARKER_LINE.search(text) is not None


def _greeting_has_unmerged_stages(repo_path: Path) -> bool:
    """True when greeting.txt still has unmerged index stages."""
    for line in git_ops.unmerged_entries(repo_path):
        # ls-files -u: <mode> <hash> <stage>\t<path>
        path = line.split("\t", 1)[-1].strip()
        if path == GREETING_FILE:
            return True
    return False


class MergeConflictScenario:
    """Leave the learner mid-merge with a conflict in ``greeting.txt``."""

    id: str = "merge-conflict"
    module: str = "git"
    title: str = "Resolve a merge conflict"
    description: str = (
        "Finish an in-progress merge on main by resolving a conflicted file "
        "into a real two-parent merge commit."
    )
    difficulty: str | None = "beginner"
    state_model: type[MergeConflictState] = MergeConflictState

    def assignment(self) -> Assignment:
        return Assignment(
            title=self.title,
            summary=(
                "Branches `main` and `feature` both changed `greeting.txt`. "
                "A merge is already in progress and conflicted. Finish the merge "
                "on `main` so the repository history is a real two-parent merge "
                "commit and `greeting.txt` contains both greetings plus the "
                "shared line."
            ),
            objectives=[
                "Remain on branch `main` with a completed merge (not mid-merge).",
                "Produce a merge commit whose parents are the original pre-merge "
                "`main` and `feature` tips.",
                "Make `greeting.txt` match the expected combined content exactly.",
                "Leave a clean working tree with no conflict markers.",
            ],
        )

    def setup(self, repo_path: Path) -> MergeConflictState:
        git_ops.init(repo_path)
        git_ops.configure_lab_repo(
            repo_path,
            hooks_path=_hooks_path_for_repo(repo_path),
        )

        _write_text(repo_path, GREETING_FILE, BASE_CONTENT)
        git_ops.add_all(repo_path)
        base_sha = git_ops.commit(repo_path, "Add greeting.txt")

        git_ops.create_branch(repo_path, "feature")

        _write_text(repo_path, GREETING_FILE, MAIN_CONTENT)
        git_ops.add_all(repo_path)
        main_tip_sha = git_ops.commit(repo_path, "Update greeting on main")

        git_ops.checkout(repo_path, "feature")
        _write_text(repo_path, GREETING_FILE, FEATURE_CONTENT)
        git_ops.add_all(repo_path)
        feature_tip_sha = git_ops.commit(repo_path, "Update greeting on feature")

        git_ops.checkout(repo_path, "main")
        result = git_ops.merge(
            repo_path,
            "feature",
            no_edit=True,
            allowed_returncodes={0, 1},
        )
        if result.returncode != 1:
            raise ScenarioSetupError(
                "Expected merge of 'feature' into 'main' to conflict, "
                f"but git exited with code {result.returncode}."
            )

        state = MergeConflictState(
            base_sha=base_sha,
            main_tip_sha=main_tip_sha,
            feature_tip_sha=feature_tip_sha,
        )
        self._verify_setup(repo_path, state)
        return state

    def _verify_setup(self, repo_path: Path, state: MergeConflictState) -> None:
        errors: list[str] = []

        if git_ops.is_detached_head(repo_path):
            errors.append("HEAD is detached; expected branch main")
        else:
            branch = git_ops.current_branch(repo_path)
            if branch != "main":
                errors.append(f"HEAD is on {branch!r}; expected 'main'")

        if not git_ops.merge_head_exists(repo_path):
            errors.append("MERGE_HEAD is missing; expected an in-progress merge")

        if not git_ops.has_unmerged_paths(repo_path):
            errors.append("Expected unmerged index entries for the conflict")

        greeting = repo_path / GREETING_FILE
        if not greeting.is_file():
            errors.append(f"{GREETING_FILE} is missing")
        else:
            text = _read_text_normalized(repo_path, GREETING_FILE)
            if not _contains_conflict_markers(text):
                errors.append(f"{GREETING_FILE} lacks conflict markers")

        for label, sha in (
            ("base_sha", state.base_sha),
            ("main_tip_sha", state.main_tip_sha),
            ("feature_tip_sha", state.feature_tip_sha),
        ):
            try:
                resolved = git_ops.rev_parse(repo_path, sha)
            except ProcessError as exc:
                errors.append(f"{label} {sha} does not resolve: {exc.message}")
                continue
            if resolved != sha:
                errors.append(f"{label} resolved to {resolved}, expected {sha}")

        try:
            if git_ops.rev_parse(repo_path, "HEAD") != state.main_tip_sha:
                errors.append("HEAD does not match recorded main_tip_sha")
            if git_ops.rev_parse(repo_path, "MERGE_HEAD") != state.feature_tip_sha:
                errors.append("MERGE_HEAD does not match recorded feature_tip_sha")
        except ProcessError as exc:
            errors.append(f"Unable to verify HEAD/MERGE_HEAD SHAs: {exc.message}")

        if errors:
            raise ScenarioSetupError(
                "merge-conflict setup postconditions failed:\n- " + "\n- ".join(errors)
            )

    def validate(self, repo_path: Path, state: MergeConflictState) -> CheckResult:
        objectives = [
            self._check_on_main(repo_path),
            self._check_no_unmerged(repo_path),
            self._check_merge_finished(repo_path),
            self._check_clean_tree(repo_path),
            self._check_merge_commit(repo_path),
            self._check_parents(repo_path, state),
            self._check_greeting_content(repo_path),
            self._check_no_markers(repo_path),
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

    def _check_no_unmerged(self, repo_path: Path) -> ObjectiveResult:
        passed = not git_ops.has_unmerged_paths(repo_path)
        return ObjectiveResult(
            id="no-unmerged",
            description="No unmerged index entries",
            passed=passed,
            detail=None if passed else "Unmerged paths remain in the index",
        )

    def _check_merge_finished(self, repo_path: Path) -> ObjectiveResult:
        passed = not git_ops.merge_head_exists(repo_path)
        return ObjectiveResult(
            id="merge-finished",
            description="MERGE_HEAD is absent (merge completed)",
            passed=passed,
            detail=None if passed else "MERGE_HEAD is still present",
        )

    def _check_clean_tree(self, repo_path: Path) -> ObjectiveResult:
        passed = git_ops.is_clean(repo_path)
        return ObjectiveResult(
            id="clean-tree",
            description="Working tree is clean",
            passed=passed,
            detail=None
            if passed
            else f"Dirty paths:\n{git_ops.status_porcelain(repo_path).rstrip()}",
        )

    def _check_merge_commit(self, repo_path: Path) -> ObjectiveResult:
        parents = git_ops.commit_parents(repo_path, "HEAD")
        passed = len(parents) == 2
        return ObjectiveResult(
            id="merge-commit",
            description="HEAD is a merge commit with exactly two parents",
            passed=passed,
            detail=None if passed else f"HEAD has {len(parents)} parent(s)",
        )

    def _check_parents(
        self, repo_path: Path, state: MergeConflictState
    ) -> ObjectiveResult:
        parents = git_ops.commit_parents(repo_path, "HEAD")
        if len(parents) != 2:
            return ObjectiveResult(
                id="merge-parents",
                description=(
                    "Merge parents match recorded main_tip_sha and feature_tip_sha"
                ),
                passed=False,
                detail=f"Expected 2 parents, found {len(parents)}",
            )
        first, second = parents
        passed = first == state.main_tip_sha and second == state.feature_tip_sha
        detail = None
        if not passed:
            detail = (
                f"parents=({first}, {second}); "
                f"expected=({state.main_tip_sha}, {state.feature_tip_sha})"
            )
        return ObjectiveResult(
            id="merge-parents",
            description=(
                "Merge parents match recorded main_tip_sha and feature_tip_sha"
            ),
            passed=passed,
            detail=detail,
        )

    def _check_greeting_content(self, repo_path: Path) -> ObjectiveResult:
        path = repo_path / GREETING_FILE
        if not path.is_file():
            return ObjectiveResult(
                id="greeting-content",
                description="greeting.txt matches expected resolved content",
                passed=False,
                detail=f"{GREETING_FILE} is missing",
            )
        actual = _read_text_normalized(repo_path, GREETING_FILE)
        passed = actual == EXPECTED_RESOLVED_CONTENT
        return ObjectiveResult(
            id="greeting-content",
            description="greeting.txt matches expected resolved content",
            passed=passed,
            detail=None if passed else "File content does not match expected text",
        )

    def _check_no_markers(self, repo_path: Path) -> ObjectiveResult:
        path = repo_path / GREETING_FILE
        if not path.is_file():
            return ObjectiveResult(
                id="no-markers",
                description="greeting.txt contains no conflict markers",
                passed=False,
                detail=f"{GREETING_FILE} is missing",
            )
        if _greeting_has_unmerged_stages(repo_path):
            return ObjectiveResult(
                id="no-markers",
                description="greeting.txt contains no conflict markers",
                passed=False,
                detail=(
                    f"{GREETING_FILE} is still unmerged in the index "
                    "(conflict not fully resolved)"
                ),
            )
        text = _read_text_normalized(repo_path, GREETING_FILE)
        passed = not _contains_conflict_markers(text)
        return ObjectiveResult(
            id="no-markers",
            description="greeting.txt contains no conflict markers",
            passed=passed,
            detail=None if passed else "Conflict markers are still present",
        )
