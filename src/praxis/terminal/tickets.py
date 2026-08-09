"""In-memory short-lived terminal tickets (not user auth)."""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass

from praxis.errors import PraxisError

DEFAULT_TICKET_TTL_SECONDS = 30


class TerminalTicketError(PraxisError):
    """Ticket missing, expired, or already used."""


@dataclass(slots=True)
class TerminalTicket:
    ticket: str
    session_id: str
    created_at: float
    expires_at: float
    consumed: bool = False


class TerminalTicketStore:
    """Process-memory, single-use terminal tickets bound to a Praxis session id."""

    def __init__(self, *, ttl_seconds: float = DEFAULT_TICKET_TTL_SECONDS) -> None:
        self._ttl = ttl_seconds
        self._tickets: dict[str, TerminalTicket] = {}

    def issue(self, session_id: str) -> TerminalTicket:
        self.purge_expired()
        token = secrets.token_urlsafe(32)
        now = time.monotonic()
        ticket = TerminalTicket(
            ticket=token,
            session_id=session_id,
            created_at=now,
            expires_at=now + self._ttl,
        )
        self._tickets[token] = ticket
        return ticket

    def consume(self, ticket_value: str) -> TerminalTicket:
        self.purge_expired()
        ticket = self._tickets.get(ticket_value)
        if ticket is None:
            raise TerminalTicketError("Invalid or unknown terminal ticket")
        if ticket.consumed:
            raise TerminalTicketError("Terminal ticket has already been used")
        if time.monotonic() > ticket.expires_at:
            del self._tickets[ticket_value]
            raise TerminalTicketError("Terminal ticket has expired")
        ticket.consumed = True
        del self._tickets[ticket_value]
        return ticket

    def purge_expired(self) -> None:
        now = time.monotonic()
        expired = [k for k, t in self._tickets.items() if now > t.expires_at]
        for key in expired:
            del self._tickets[key]

    @property
    def ttl_seconds(self) -> float:
        return self._ttl
