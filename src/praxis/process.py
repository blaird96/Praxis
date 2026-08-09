"""Safe subprocess execution without shell invocation."""

from __future__ import annotations

import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from praxis.errors import ProcessError

DEFAULT_TIMEOUT_SECONDS = 30.0


@dataclass(frozen=True, slots=True)
class ProcessResult:
    argv: list[str]
    returncode: int
    stdout: str
    stderr: str


def run(
    argv: Sequence[str],
    *,
    cwd: Path | str | None = None,
    allowed_returncodes: set[int] | None = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    env: Mapping[str, str] | None = None,
) -> ProcessResult:
    """Run ``argv`` without a shell.

    Success means the process exit code is in ``allowed_returncodes``
    (default ``{0}``). Unexpected codes and timeouts raise ``ProcessError``.
    """
    if not argv:
        raise ProcessError("Cannot run empty argv")

    command = [str(part) for part in argv]
    allowed = allowed_returncodes if allowed_returncodes is not None else {0}
    workdir = str(cwd) if cwd is not None else None

    try:
        completed = subprocess.run(
            command,
            cwd=workdir,
            capture_output=True,
            text=True,
            shell=False,
            timeout=timeout,
            env=dict(env) if env is not None else None,
            check=False,
        )
    except FileNotFoundError as exc:
        raise ProcessError(
            f"Executable not found: {command[0]}",
            argv=command,
        ) from exc
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""
        if isinstance(stdout, bytes):
            stdout = stdout.decode(errors="replace")
        if isinstance(stderr, bytes):
            stderr = stderr.decode(errors="replace")
        raise ProcessError(
            f"Command timed out after {timeout}s: {' '.join(command)}",
            argv=command,
            stdout=stdout,
            stderr=stderr,
        ) from exc

    result = ProcessResult(
        argv=command,
        returncode=completed.returncode,
        stdout=completed.stdout or "",
        stderr=completed.stderr or "",
    )

    if result.returncode not in allowed:
        detail = result.stderr.strip() or result.stdout.strip() or "(no output)"
        raise ProcessError(
            f"Command failed with exit code {result.returncode}: "
            f"{' '.join(command)}\n{detail}",
            argv=command,
            returncode=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
        )

    return result
