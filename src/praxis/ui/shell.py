"""Platform helpers for launching a lab shell in the exercise repository."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


class ShellLaunchError(Exception):
    """Lab shell could not be started."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def resolve_shell_command() -> list[str]:
    """Return argv for an interactive shell.

    Prefer ``PRAXIS_SHELL`` when set. On Windows, try ``pwsh``, ``powershell``,
    then ``cmd``. On Unix-like systems, prefer ``$SHELL`` then ``/bin/sh``.
    """
    override = os.environ.get("PRAXIS_SHELL")
    if override:
        return [override]

    if sys.platform == "win32":
        for candidate in ("pwsh", "powershell", "cmd"):
            path = shutil.which(candidate)
            if path:
                if candidate == "cmd":
                    return [path]
                return [path, "-NoLogo"]
        raise ShellLaunchError(
            "No interactive shell found (tried pwsh, powershell, cmd). "
            "Set PRAXIS_SHELL to an executable."
        )

    shell = os.environ.get("SHELL") or "/bin/sh"
    return [shell]


def run_lab_shell(repo_path: Path) -> int:
    """Run an interactive shell with cwd set to ``repo_path``.

    Returns the shell exit code. Raises ``ShellLaunchError`` if the shell
    cannot be started.
    """
    cwd = Path(repo_path).resolve()
    if not cwd.is_dir():
        raise ShellLaunchError(f"Exercise repository does not exist: {cwd}")

    command = resolve_shell_command()
    try:
        completed = subprocess.run(
            command,
            cwd=str(cwd),
            check=False,
            shell=False,
        )
    except FileNotFoundError as exc:
        raise ShellLaunchError(f"Shell executable not found: {command[0]}") from exc
    except OSError as exc:
        raise ShellLaunchError(f"Failed to launch lab shell: {exc}") from exc

    return int(completed.returncode)
