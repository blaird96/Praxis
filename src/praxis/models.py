"""Shared durable models for sessions and results."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class SessionStatus(StrEnum):
    PROVISIONAL = "provisional"
    ACTIVE = "active"
    FAILED = "failed"


class Session(BaseModel):
    """Durable session record stored under workspace/.praxis/session.json."""

    session_id: str
    module: str
    scenario: str
    created_at: datetime
    workspace_path: Path
    repo_path: Path
    status: SessionStatus = SessionStatus.PROVISIONAL
    scenario_state: dict[str, Any] | None = None


class ObjectiveResult(BaseModel):
    id: str
    description: str
    passed: bool
    detail: str | None = None


class CheckResult(BaseModel):
    passed: bool
    objectives: list[ObjectiveResult] = Field(default_factory=list)


class Assignment(BaseModel):
    title: str
    summary: str
    objectives: list[str] = Field(default_factory=list)
