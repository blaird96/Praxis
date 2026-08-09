"""POSIX PTY terminal session using the standard library."""

from __future__ import annotations

import asyncio
import contextlib
import errno
import fcntl
import os
import signal
import struct
import termios
from pathlib import Path

from praxis.terminal.factory import TerminalSpawnError


def _set_winsize(fd: int, rows: int, cols: int) -> None:
    packed = struct.pack("HHHH", rows, cols, 0, 0)
    fcntl.ioctl(fd, termios.TIOCSWINSZ, packed)


class PosixTerminalSession:
    """Async PTY session backed by ``pty.openpty`` + subprocess."""

    def __init__(
        self,
        *,
        master_fd: int,
        process: asyncio.subprocess.Process,
    ) -> None:
        self._master_fd = master_fd
        self._process = process
        self._closed = False
        self._exit_code: int | None = None
        self._write_lock = asyncio.Lock()

    @classmethod
    async def spawn_async(
        cls,
        argv: list[str],
        *,
        cwd: Path,
        cols: int,
        rows: int,
    ) -> PosixTerminalSession:
        import pty

        cwd_resolved = cwd.resolve()
        if not cwd_resolved.is_dir():
            raise TerminalSpawnError(
                f"Exercise repo is not a directory: {cwd_resolved}"
            )

        try:
            master_fd, slave_fd = pty.openpty()
            _set_winsize(slave_fd, rows, cols)
        except OSError as exc:
            raise TerminalSpawnError(f"Failed to open PTY: {exc}") from exc

        try:
            process = await asyncio.create_subprocess_exec(
                *argv,
                cwd=str(cwd_resolved),
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                start_new_session=True,
            )
        except Exception as exc:
            os.close(master_fd)
            os.close(slave_fd)
            raise TerminalSpawnError(f"Failed to spawn shell: {exc}") from exc
        finally:
            with contextlib.suppress(OSError):
                os.close(slave_fd)

        flags = fcntl.fcntl(master_fd, fcntl.F_GETFL)
        fcntl.fcntl(master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)
        return cls(master_fd=master_fd, process=process)

    async def read(self) -> bytes:
        if self._closed:
            return b""
        loop = asyncio.get_running_loop()
        future: asyncio.Future[bytes] = loop.create_future()

        def _on_readable() -> None:
            try:
                data = os.read(self._master_fd, 4096)
            except OSError as exc:
                if exc.errno in {errno.EAGAIN, errno.EWOULDBLOCK}:
                    return
                if not future.done():
                    future.set_result(b"")
                return
            if not future.done():
                future.set_result(data)

        loop.add_reader(self._master_fd, _on_readable)
        try:
            data = await future
        finally:
            with contextlib.suppress(Exception):
                loop.remove_reader(self._master_fd)
        if not data:
            self._closed = True
        return data

    async def write(self, data: bytes) -> None:
        if self._closed or not data:
            return
        async with self._write_lock:
            view = memoryview(data)
            while len(view):
                try:
                    written = os.write(self._master_fd, view)
                except OSError as exc:
                    if exc.errno in {errno.EAGAIN, errno.EWOULDBLOCK}:
                        await asyncio.sleep(0.01)
                        continue
                    raise
                view = view[written:]

    async def resize(self, cols: int, rows: int) -> None:
        if self._closed:
            return
        await asyncio.to_thread(_set_winsize, self._master_fd, rows, cols)

    async def wait(self) -> int:
        if self._exit_code is not None:
            return self._exit_code
        code = await self._process.wait()
        self._exit_code = int(code) if code is not None else 0
        self._closed = True
        return self._exit_code

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._process.returncode is None:
            with contextlib.suppress(ProcessLookupError, OSError):
                os.killpg(self._process.pid, signal.SIGTERM)
            try:
                await asyncio.wait_for(self._process.wait(), timeout=1.0)
            except TimeoutError:
                with contextlib.suppress(ProcessLookupError, OSError):
                    os.killpg(self._process.pid, signal.SIGKILL)
                await self._process.wait()
        self._exit_code = (
            int(self._process.returncode) if self._process.returncode is not None else 0
        )
        with contextlib.suppress(OSError):
            os.close(self._master_fd)

    def closed(self) -> bool:
        return self._closed or self._process.returncode is not None
