"""Track live terminal sessions for cleanup on reset/shutdown."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from praxis.terminal.base import TerminalSession


@dataclass(slots=True)
class TrackedTerminal:
    connection_id: str
    session_id: str
    terminal: TerminalSession
    tasks: list[asyncio.Task[None]] = field(default_factory=list)


class TerminalRegistry:
    """In-process registry of open WebSocket-backed PTY sessions."""

    def __init__(self) -> None:
        self._by_connection: dict[str, TrackedTerminal] = {}
        self._lock = asyncio.Lock()

    async def register(self, tracked: TrackedTerminal) -> None:
        async with self._lock:
            self._by_connection[tracked.connection_id] = tracked

    async def unregister(self, connection_id: str) -> TrackedTerminal | None:
        async with self._lock:
            return self._by_connection.pop(connection_id, None)

    async def close_connection(self, connection_id: str) -> None:
        tracked = await self.unregister(connection_id)
        if tracked is None:
            return
        await self._shutdown(tracked)

    async def close_for_session(self, session_id: str) -> int:
        async with self._lock:
            victims = [
                t for t in self._by_connection.values() if t.session_id == session_id
            ]
            for t in victims:
                self._by_connection.pop(t.connection_id, None)
        for tracked in victims:
            await self._shutdown(tracked)
        return len(victims)

    async def close_all(self) -> None:
        async with self._lock:
            victims = list(self._by_connection.values())
            self._by_connection.clear()
        for tracked in victims:
            await self._shutdown(tracked)

    async def _shutdown(self, tracked: TrackedTerminal) -> None:
        # Close the PTY first so blocked readers unblock before task cancel.
        try:
            await tracked.terminal.close()
        except Exception:
            pass
        loop = asyncio.get_running_loop()
        same_loop: list[asyncio.Task[None]] = []
        for task in tracked.tasks:
            try:
                task.cancel()
                if task.get_loop() is loop:
                    same_loop.append(task)
            except Exception:
                pass
        if same_loop:
            await asyncio.gather(*same_loop, return_exceptions=True)

    def connection_count(self) -> int:
        return len(self._by_connection)
