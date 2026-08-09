"""Thin git argv helpers built on ``praxis.process.run``.

Does not wrap a repository object — callers pass ``repo_path`` explicitly.
Never modifies the user's global git configuration.
"""

from __future__ import annotations

from pathlib import Path

from praxis.process import ProcessResult, run

DEFAULT_LAB_USER_NAME = "Praxis Lab"
DEFAULT_LAB_USER_EMAIL = "praxis@example.invalid"


def _git(
    repo_path: Path,
    *args: str,
    allowed_returncodes: set[int] | None = None,
) -> ProcessResult:
    return run(
        ["git", *args],
        cwd=repo_path,
        allowed_returncodes=allowed_returncodes,
    )


def init(repo_path: Path) -> None:
    """Initialize a new repository with default branch ``main``."""
    repo_path.mkdir(parents=True, exist_ok=True)
    _git(repo_path, "init", "-b", "main")


def configure_lab_repo(
    repo_path: Path,
    *,
    hooks_path: Path,
    user_name: str = DEFAULT_LAB_USER_NAME,
    user_email: str = DEFAULT_LAB_USER_EMAIL,
) -> None:
    """Apply repository-local lab isolation settings.

    Sets only ``--local`` config values. ``hooks_path`` should be an empty
    Praxis-controlled directory outside the exercise working tree.
    """
    hooks_path.mkdir(parents=True, exist_ok=True)
    _git(repo_path, "config", "--local", "user.name", user_name)
    _git(repo_path, "config", "--local", "user.email", user_email)
    _git(repo_path, "config", "--local", "commit.gpgSign", "false")
    _git(repo_path, "config", "--local", "core.autocrlf", "false")
    _git(repo_path, "config", "--local", "core.hooksPath", str(hooks_path.resolve()))


def get_local_config(repo_path: Path, key: str) -> str:
    """Read a repository-local config value."""
    result = _git(repo_path, "config", "--local", "--get", key)
    return result.stdout.strip()


def add_all(repo_path: Path) -> None:
    _git(repo_path, "add", "-A")


def commit(repo_path: Path, message: str) -> str:
    """Create a commit and return its SHA."""
    _git(repo_path, "commit", "-m", message)
    return rev_parse(repo_path, "HEAD")


def create_branch(repo_path: Path, name: str) -> None:
    """Create a new branch at HEAD without switching to it."""
    _git(repo_path, "branch", name)


def checkout(repo_path: Path, ref: str) -> None:
    """Check out an existing branch or commit (``git checkout``)."""
    _git(repo_path, "checkout", ref)


def switch_branch(repo_path: Path, name: str, *, create: bool = False) -> None:
    """Switch branches using ``git switch``."""
    args = ["switch"]
    if create:
        args.append("-c")
    args.append(name)
    _git(repo_path, *args)


def merge(
    repo_path: Path,
    branch: str,
    *,
    allowed_returncodes: set[int] | None = None,
) -> ProcessResult:
    """Merge ``branch`` into HEAD.

    Callers expecting conflicts should pass ``allowed_returncodes={0, 1}``.
    """
    return _git(
        repo_path,
        "merge",
        "--no-ff",
        "--no-edit",
        branch,
        allowed_returncodes=allowed_returncodes,
    )


def rev_parse(repo_path: Path, ref: str) -> str:
    result = _git(repo_path, "rev-parse", ref)
    return result.stdout.strip()


def current_branch(repo_path: Path) -> str:
    """Return the short branch name for HEAD, or raise if detached."""
    result = _git(repo_path, "symbolic-ref", "--short", "HEAD")
    return result.stdout.strip()


def is_detached_head(repo_path: Path) -> bool:
    result = _git(
        repo_path,
        "symbolic-ref",
        "-q",
        "HEAD",
        allowed_returncodes={0, 1},
    )
    return result.returncode != 0


def commit_parents(repo_path: Path, ref: str = "HEAD") -> list[str]:
    """Return parent SHAs for ``ref`` (empty for a root commit)."""
    result = _git(
        repo_path,
        "rev-list",
        "--parents",
        "-n",
        "1",
        ref,
    )
    parts = result.stdout.strip().split()
    if not parts:
        return []
    # Output: <commit> [parent...]
    return parts[1:]


def unmerged_entries(repo_path: Path) -> list[str]:
    """Return porcelain lines from ``git ls-files -u`` (empty if none)."""
    result = _git(repo_path, "ls-files", "-u")
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    return lines


def has_unmerged_paths(repo_path: Path) -> bool:
    return bool(unmerged_entries(repo_path))


def status_porcelain(repo_path: Path) -> str:
    result = _git(repo_path, "status", "--porcelain")
    return result.stdout


def is_clean(repo_path: Path) -> bool:
    return status_porcelain(repo_path) == ""


def merge_head_exists(repo_path: Path) -> bool:
    """True when a merge is in progress (``.git/MERGE_HEAD`` present)."""
    result = _git(
        repo_path,
        "rev-parse",
        "-q",
        "--verify",
        "MERGE_HEAD",
        allowed_returncodes={0, 1},
    )
    return result.returncode == 0
