"""In-memory fake PTY for WebSocket lifecycle tests."""

from __future__ import annotations

import asyncio
from pathlib import Path


class FakeTerminalSession:
    """Test double that records writes/resizes and streams scripted output."""

    def __init__(
        self,
        *,
        cwd: Path,
        cols: int,
        rows: int,
        output: bytes = b"",
        exit_code: int = 0,
    ) -> None:
        self.cwd = cwd
        self.cols = cols
        self.rows = rows
        self.written: list[bytes] = []
        self.resizes: list[tuple[int, int]] = []
        self._output = output
        self._exit_code = exit_code
        self._closed = False
        self._output_queue: asyncio.Queue[bytes | None] = asyncio.Queue()
        if output:
            self._output_queue.put_nowait(output)

    def push_output(self, data: bytes) -> None:
        self._output_queue.put_nowait(data)

    def end_output(self) -> None:
        self._output_queue.put_nowait(None)

    async def read(self) -> bytes:
        if self._closed:
            return b""
        item = await self._output_queue.get()
        if item is None:
            self._closed = True
            return b""
        return item

    async def write(self, data: bytes) -> None:
        if self._closed:
            return
        self.written.append(data)

    async def resize(self, cols: int, rows: int) -> None:
        self.cols = cols
        self.rows = rows
        self.resizes.append((cols, rows))

    async def wait(self) -> int:
        deadline = asyncio.get_running_loop().time() + 2.0
        while not self._closed:
            if asyncio.get_running_loop().time() > deadline:
                self._closed = True
                break
            await asyncio.sleep(0.01)
        return self._exit_code

    async def close(self) -> None:
        self._closed = True
        self.end_output()

    def closed(self) -> bool:
        return self._closed
