"""Terminal subsystem: real interactive PTY/ConPTY for exercise shells."""

from __future__ import annotations

from praxis.terminal.base import TerminalSession
from praxis.terminal.factory import create_terminal_session, resolve_shell
from praxis.terminal.registry import TerminalRegistry
from praxis.terminal.tickets import TerminalTicketStore

__all__ = [
    "TerminalRegistry",
    "TerminalSession",
    "TerminalTicketStore",
    "create_terminal_session",
    "resolve_shell",
]
