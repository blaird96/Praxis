"""Thin Scenario protocol shared by training modules."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, TypeVar, runtime_checkable

from pydantic import BaseModel

from praxis.models import Assignment, CheckResult

ScenarioState = TypeVar("ScenarioState", bound=BaseModel)


@runtime_checkable
class Scenario(Protocol[ScenarioState]):
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

    def assignment(self) -> Assignment:
        """Return the learner-facing assignment (end state, not a command recipe)."""

    def setup(self, repo_path: Path) -> ScenarioState:
        """Construct the lab environment; return immutable setup state."""

    def validate(self, repo_path: Path, state: ScenarioState) -> CheckResult:
        """Deterministically check whether objectives are satisfied."""
