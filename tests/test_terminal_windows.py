"""Windows ConPTY smoke test (real shell)."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import pytest

from praxis.terminal.factory import create_terminal_session, resolve_shell

pytestmark = [
    pytest.mark.skipif(
        sys.platform != "win32", reason="ConPTY integration is Windows-only"
    ),
    pytest.mark.skipif(
        os.environ.get("PRAXIS_SKIP_CONPTY") == "1",
        reason="PRAXIS_SKIP_CONPTY=1",
    ),
]


@pytest.mark.asyncio
async def test_windows_conpty_smoke(tmp_path: Path) -> None:
    async def _run() -> None:
        argv = resolve_shell()
        term = await create_terminal_session(tmp_path, cols=80, rows=24, argv=argv)
        marker = tmp_path / "praxis_term_marker.txt"
        try:
            # Drain a bit of banner (proves PTY output flows).
            saw_output = False
            for _ in range(6):
                try:
                    data = await asyncio.wait_for(term.read(), timeout=0.6)
                except TimeoutError:
                    break
                if data:
                    saw_output = True
                    break

            await term.resize(100, 30)

            # Prove cwd is the exercise repo by creating a marker file via the shell.
            if any(
                "powershell" in part.lower() or "pwsh" in part.lower() for part in argv
            ):
                await term.write(
                    b"Set-Content -Path praxis_term_marker.txt -Value ok\r\n"
                )
            else:
                await term.write(b"echo ok>praxis_term_marker.txt\r\n")

            deadline = asyncio.get_running_loop().time() + 5.0
            while asyncio.get_running_loop().time() < deadline:
                if marker.is_file():
                    break
                try:
                    await asyncio.wait_for(term.read(), timeout=0.3)
                except TimeoutError:
                    pass

            assert saw_output or marker.is_file(), "expected PTY output or marker file"
            assert marker.is_file(), "shell did not create marker in exercise cwd"
            assert "ok" in marker.read_text(encoding="utf-8", errors="ignore").lower()
        finally:
            await asyncio.wait_for(term.close(), timeout=3.0)
            assert term.closed()

    await asyncio.wait_for(_run(), timeout=20.0)
