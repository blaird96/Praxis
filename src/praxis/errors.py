"""Praxis error types and process exit codes."""

from __future__ import annotations


class ExitCode:
    """Process exit codes used by the CLI."""

    SUCCESS = 0
    CHECK_FAILED = 1
    ERROR = 2


class PraxisError(Exception):
    """Base error for expected Praxis failures."""

    exit_code: int = ExitCode.ERROR

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class SessionNotFoundError(PraxisError):
    """No resolvable Praxis session for the current context."""


class WorkspaceError(PraxisError):
    """Workspace layout or path-safety failure."""


class ProcessError(PraxisError):
    """Subprocess invocation failed or returned an unexpected code."""

    def __init__(
        self,
        message: str,
        *,
        argv: list[str] | None = None,
        returncode: int | None = None,
        stdout: str = "",
        stderr: str = "",
    ) -> None:
        super().__init__(message)
        self.argv = argv or []
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class UnknownModuleError(PraxisError):
    """Requested training module is not registered."""


class UnknownScenarioError(PraxisError):
    """Requested scenario is not registered for its module."""


class ScenarioSetupError(PraxisError):
    """Scenario setup failed to establish or verify the expected starting state."""


class ScenarioStateError(PraxisError):
    """Persisted scenario state is missing or cannot be rehydrated."""
