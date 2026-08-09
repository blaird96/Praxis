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
    no_ff: bool = False,
    no_edit: bool = False,
    allowed_returncodes: set[int] | None = None,
) -> ProcessResult:
    """Merge ``branch`` into HEAD.

    Defaults stay close to ordinary ``git merge``. Callers expecting conflicts
    should pass ``allowed_returncodes={0, 1}``. Non-interactive lab setup should
    pass ``no_edit=True`` explicitly when a merge commit message would be needed.
    """
    args = ["merge"]
    if no_ff:
        args.append("--no-ff")
    if no_edit:
        args.append("--no-edit")
    args.append(branch)
    return _git(
        repo_path,
        *args,
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


def add_paths(repo_path: Path, *paths: str) -> None:
    """Stage specific paths (``git add -- <paths>``)."""
    if not paths:
        raise ValueError("add_paths requires at least one path")
    _git(repo_path, "add", "--", *paths)


def show(repo_path: Path, objectish: str) -> str:
    """Return ``git show`` stdout for ``objectish`` (e.g. ``HEAD:app.py``)."""
    result = _git(repo_path, "show", objectish)
    return result.stdout


def cat_file_exists(repo_path: Path, objectish: str) -> bool:
    result = _git(
        repo_path,
        "cat-file",
        "-e",
        objectish,
        allowed_returncodes={0, 1},
    )
    return result.returncode == 0


def rev_parse_verify(repo_path: Path, ref: str) -> str | None:
    """Return resolved SHA for ``ref``, or None if it does not exist."""
    result = _git(
        repo_path,
        "rev-parse",
        "-q",
        "--verify",
        ref,
        allowed_returncodes={0, 1},
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def is_ancestor(repo_path: Path, maybe_ancestor: str, descendant: str) -> bool:
    """True when ``maybe_ancestor`` is an ancestor of ``descendant``."""
    result = _git(
        repo_path,
        "merge-base",
        "--is-ancestor",
        maybe_ancestor,
        descendant,
        allowed_returncodes={0, 1},
    )
    return result.returncode == 0


def merge_base(repo_path: Path, a: str, b: str) -> str:
    result = _git(repo_path, "merge-base", a, b)
    return result.stdout.strip()


def commit_tree_sha(repo_path: Path, ref: str = "HEAD") -> str:
    """Return the tree OID for ``ref``."""
    return rev_parse(repo_path, f"{ref}^{{tree}}")


def reset(
    repo_path: Path,
    target: str,
    *,
    mode: str = "mixed",
) -> None:
    """Reset HEAD to ``target`` with ``--soft``, ``--mixed``, or ``--hard``."""
    if mode not in {"soft", "mixed", "hard"}:
        raise ValueError(f"Unsupported reset mode: {mode}")
    _git(repo_path, "reset", f"--{mode}", target)


def restore(repo_path: Path, *paths: str) -> None:
    """Restore paths in the working tree from HEAD (``git restore``)."""
    if not paths:
        raise ValueError("restore requires at least one path")
    _git(repo_path, "restore", "--", *paths)


def rebase(
    repo_path: Path,
    upstream: str,
    *,
    allowed_returncodes: set[int] | None = None,
) -> ProcessResult:
    return _git(
        repo_path,
        "rebase",
        upstream,
        allowed_returncodes=allowed_returncodes,
    )


def rebase_continue(
    repo_path: Path,
    *,
    allowed_returncodes: set[int] | None = None,
) -> ProcessResult:
    return _git(
        repo_path,
        "-c",
        "core.editor=true",
        "rebase",
        "--continue",
        allowed_returncodes=allowed_returncodes,
    )


def rebase_in_progress(repo_path: Path) -> bool:
    git_dir = Path(
        _git(repo_path, "rev-parse", "--git-path", "rebase-merge").stdout.strip()
    )
    if not git_dir.is_absolute():
        git_dir = repo_path / git_dir
    if git_dir.exists():
        return True
    apply_dir = Path(
        _git(repo_path, "rev-parse", "--git-path", "rebase-apply").stdout.strip()
    )
    if not apply_dir.is_absolute():
        apply_dir = repo_path / apply_dir
    return apply_dir.exists()


def cherry_pick(
    repo_path: Path,
    commit: str,
    *,
    allowed_returncodes: set[int] | None = None,
) -> ProcessResult:
    return _git(
        repo_path,
        "cherry-pick",
        commit,
        allowed_returncodes=allowed_returncodes,
    )


def stash_push(repo_path: Path, message: str | None = None) -> None:
    args = ["stash", "push", "-u"]
    if message:
        args.extend(["-m", message])
    _git(repo_path, *args)


def stash_pop(repo_path: Path) -> None:
    _git(repo_path, "stash", "pop")


def stash_list(repo_path: Path) -> list[str]:
    result = _git(repo_path, "stash", "list")
    return [line for line in result.stdout.splitlines() if line.strip()]


def init_bare(bare_path: Path) -> None:
    """Create a bare repository at ``bare_path``."""
    bare_path.parent.mkdir(parents=True, exist_ok=True)
    run(["git", "init", "--bare", "-b", "main", str(bare_path)])


def remote_add(repo_path: Path, name: str, url: str) -> None:
    _git(repo_path, "remote", "add", name, url)


def remote_set_url(repo_path: Path, name: str, url: str) -> None:
    _git(repo_path, "remote", "set-url", name, url)


def fetch(repo_path: Path, remote: str = "origin") -> None:
    _git(repo_path, "fetch", remote)


def pull(
    repo_path: Path,
    remote: str = "origin",
    branch: str = "main",
    *,
    ff_only: bool = False,
    allowed_returncodes: set[int] | None = None,
) -> ProcessResult:
    args = ["pull"]
    if ff_only:
        args.append("--ff-only")
    args.extend([remote, branch])
    return _git(repo_path, *args, allowed_returncodes=allowed_returncodes)


def push(
    repo_path: Path,
    remote: str = "origin",
    refspec: str = "main",
    *,
    set_upstream: bool = False,
) -> None:
    args = ["push"]
    if set_upstream:
        args.append("-u")
    args.extend([remote, refspec])
    _git(repo_path, *args)


def branch_upstream(repo_path: Path, branch: str = "main") -> str | None:
    result = _git(
        repo_path,
        "rev-parse",
        "--abbrev-ref",
        f"{branch}@{{upstream}}",
        allowed_returncodes={0, 1},
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def set_upstream(repo_path: Path, branch: str, upstream: str) -> None:
    """Set ``branch`` to track ``upstream`` (e.g. ``origin/main``)."""
    _git(repo_path, "branch", f"--set-upstream-to={upstream}", branch)


def delete_branch(repo_path: Path, name: str, *, force: bool = False) -> None:
    flag = "-D" if force else "-d"
    _git(repo_path, "branch", flag, name)


def reflog(repo_path: Path, ref: str = "HEAD", *, max_count: int = 20) -> list[str]:
    result = _git(repo_path, "reflog", ref, f"-n{max_count}")
    return [line for line in result.stdout.splitlines() if line.strip()]


def rev_list(repo_path: Path, *args: str) -> list[str]:
    result = _git(repo_path, "rev-list", *args)
    return [line for line in result.stdout.splitlines() if line.strip()]


def clone(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    run(["git", "clone", url, str(destination)])
