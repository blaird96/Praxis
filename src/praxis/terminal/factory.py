"""Shell executable selection and terminal factory."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

from praxis.errors import PraxisError
from praxis.terminal.base import DEFAULT_COLS, DEFAULT_ROWS, TerminalSession


class TerminalSpawnError(PraxisError):
    """Failed to spawn an interactive shell in a PTY."""


def _valid_executable(path: str | None) -> str | None:
    if not path:
        return None
    candidate = Path(path)
    if candidate.is_file():
        return str(candidate.resolve())
    found = shutil.which(path)
    return found


def resolve_shell() -> list[str]:
    """Return argv for the interactive shell (executable + no profile flags)."""
    configured = _valid_executable(os.environ.get("PRAXIS_SHELL"))
    if configured:
        return [configured]

    if sys.platform == "win32":
        for name in ("pwsh", "powershell", "cmd"):
            found = _valid_executable(name)
            if found:
                if name in {"pwsh", "powershell"}:
                    return [found, "-NoLogo"]
                return [found]
        raise TerminalSpawnError("No Windows shell found (pwsh/powershell/cmd)")

    shell = _valid_executable(os.environ.get("SHELL"))
    if shell:
        return [shell]
    if Path("/bin/sh").is_file():
        return ["/bin/sh"]
    raise TerminalSpawnError("No POSIX shell found")


async def create_terminal_session(
    cwd: Path,
    *,
    cols: int = DEFAULT_COLS,
    rows: int = DEFAULT_ROWS,
    argv: list[str] | None = None,
) -> TerminalSession:
    """Spawn a platform PTY session with cwd set to the exercise repo."""
    command = argv or resolve_shell()
    if sys.platform == "win32":
        from praxis.terminal.windows import WindowsTerminalSession

        return await WindowsTerminalSession.spawn_async(
            command, cwd=cwd, cols=cols, rows=rows
        )

    from praxis.terminal.posix import PosixTerminalSession

    return await PosixTerminalSession.spawn_async(
        command, cwd=cwd, cols=cols, rows=rows
    )
