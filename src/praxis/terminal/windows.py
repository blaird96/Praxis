"""Windows ConPTY terminal session via pywinpty."""

from __future__ import annotations

import asyncio
import contextlib
import threading
from pathlib import Path

from praxis.terminal.factory import TerminalSpawnError


class WindowsTerminalSession:
    """Async wrapper around ``winpty.PtyProcess`` (ConPTY backend).

    pywinpty ``read()`` blocks indefinitely, so a dedicated daemon thread pushes
    output into an asyncio queue. Closing the process unblocks the reader.
    """

    def __init__(self, process: object) -> None:
        self._process = process
        self._closed = False
        self._exit_code: int | None = None
        self._write_lock = asyncio.Lock()
        self._loop = asyncio.get_running_loop()
        self._queue: asyncio.Queue[bytes | None] = asyncio.Queue()
        self._reader = threading.Thread(
            target=self._reader_loop,
            name="praxis-winpty-reader",
            daemon=True,
        )
        self._reader.start()

    @classmethod
    def spawn_process(
        cls,
        argv: list[str],
        *,
        cwd: Path,
        cols: int,
        rows: int,
    ) -> object:
        """Create the underlying PtyProcess (may be called off the event loop)."""
        try:
            from winpty import PtyProcess
        except ImportError as exc:
            raise TerminalSpawnError(
                "pywinpty is required for the Windows terminal"
            ) from exc

        cwd_resolved = cwd.resolve()
        if not cwd_resolved.is_dir():
            raise TerminalSpawnError(
                f"Exercise repo is not a directory: {cwd_resolved}"
            )

        try:
            return PtyProcess.spawn(
                argv,
                cwd=str(cwd_resolved),
                dimensions=(rows, cols),
            )
        except Exception as exc:
            raise TerminalSpawnError(f"Failed to spawn shell: {exc}") from exc

    @classmethod
    async def spawn_async(
        cls,
        argv: list[str],
        *,
        cwd: Path,
        cols: int,
        rows: int,
    ) -> WindowsTerminalSession:
        process = await asyncio.to_thread(
            cls.spawn_process, argv, cwd=cwd, cols=cols, rows=rows
        )
        return cls(process)

    def _reader_loop(self) -> None:
        try:
            while not self._closed:
                try:
                    text = self._process.read(4096)  # type: ignore[attr-defined]
                except EOFError:
                    break
                except Exception:
                    break
                if not text:
                    try:
                        alive = bool(self._process.isalive())  # type: ignore[attr-defined]
                    except Exception:
                        alive = False
                    if not alive:
                        break
                    # Avoid busy-spinning when the backend returns empty reads.
                    threading.Event().wait(0.02)
                    continue
                data = (
                    text
                    if isinstance(text, bytes)
                    else text.encode("utf-8", errors="replace")
                )
                self._loop.call_soon_threadsafe(self._queue.put_nowait, data)
        finally:
            self._loop.call_soon_threadsafe(self._queue.put_nowait, None)

    async def read(self) -> bytes:
        if self._closed and self._queue.empty():
            return b""
        item = await self._queue.get()
        if item is None:
            self._closed = True
            return b""
        return item

    async def write(self, data: bytes) -> None:
        if self._closed or not data:
            return
        text = data.decode("utf-8", errors="replace")
        async with self._write_lock:
            await asyncio.to_thread(self._process.write, text)  # type: ignore[attr-defined]

    async def resize(self, cols: int, rows: int) -> None:
        if self._closed:
            return
        await asyncio.to_thread(self._process.setwinsize, rows, cols)  # type: ignore[attr-defined]

    async def wait(self) -> int:
        if self._exit_code is not None:
            return self._exit_code
        code = await asyncio.to_thread(self._process.wait)  # type: ignore[attr-defined]
        self._exit_code = int(code) if code is not None else 0
        self._closed = True
        return self._exit_code

    async def close(self) -> None:
        if self._exit_code is not None:
            return
        self._closed = True
        try:
            await asyncio.to_thread(self._process.terminate, True)  # type: ignore[attr-defined]
        except Exception:
            with contextlib.suppress(Exception):
                await asyncio.to_thread(self._process.close, True)  # type: ignore[attr-defined]
        try:
            self._exit_code = int(
                await asyncio.wait_for(
                    asyncio.to_thread(self._process.wait),  # type: ignore[attr-defined]
                    timeout=2.0,
                )
            )
        except Exception:
            self._exit_code = -1
        with contextlib.suppress(asyncio.QueueFull):
            self._queue.put_nowait(None)

    def closed(self) -> bool:
        if self._closed and self._exit_code is not None:
            return True
        try:
            return not bool(self._process.isalive())  # type: ignore[attr-defined]
        except Exception:
            return True
