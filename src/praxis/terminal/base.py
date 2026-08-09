"""Terminal session protocol and shared constants."""

from __future__ import annotations

from typing import Protocol

# Resize bounds (reject absurd browser dimensions).
MIN_COLS, MAX_COLS = 10, 500
MIN_ROWS, MAX_ROWS = 5, 200
DEFAULT_COLS, DEFAULT_ROWS = 80, 24


class TerminalSession(Protocol):
    """Minimal async interface over a platform PTY/ConPTY."""

    async def read(self) -> bytes:
        """Block until some PTY output is available (or empty on EOF)."""

    async def write(self, data: bytes) -> None:
        """Write bytes to the PTY stdin."""

    async def resize(self, cols: int, rows: int) -> None:
        """Resize the pseudo-terminal."""

    async def wait(self) -> int:
        """Wait for the child process to exit; return exit code."""

    async def close(self) -> None:
        """Terminate the child and release PTY resources."""

    def closed(self) -> bool:
        """True after close or natural exit."""
