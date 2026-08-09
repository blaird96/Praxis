"""Git training module package."""

from __future__ import annotations

from . import git_ops
from .scenarios.merge_conflict import MergeConflictScenario

merge_conflict_scenario = MergeConflictScenario()

__all__ = ["git_ops", "MergeConflictScenario", "merge_conflict_scenario"]
