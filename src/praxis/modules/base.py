"""Thin Scenario protocol shared by training modules."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, TypeVar, runtime_checkable

from pydantic import BaseModel

from praxis.models import Assignment, CheckResult

StateT = TypeVar("StateT", bound=BaseModel)


@runtime_checkable
class Scenario(Protocol[StateT]):
    """Deterministic lab scenario: setup → user work → validate."""

    @property
    def id(self) -> str:
        """Scenario identifier within its module (e.g. ``merge-conflict``)."""

    @property
    def module(self) -> str:
        """Module identifier (e.g. ``git``)."""

    @property
    def title(self) -> str:
        """Short human-readable title."""

    @property
    def state_model(self) -> type[StateT]:
        """Pydantic model used to rehydrate persisted setup state."""

    def assignment(self) -> Assignment:
        """Return the learner-facing assignment (end state, not a command recipe)."""

    def setup(self, repo_path: Path) -> StateT:
        """Construct the lab environment; return immutable setup state.

        A successful return means setup postconditions have already been verified.
        """

    def validate(self, repo_path: Path, state: StateT) -> CheckResult:
        """Deterministically check whether objectives are satisfied."""
