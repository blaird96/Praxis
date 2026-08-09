"""API request/response schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = "ok"


class ScenarioInfo(BaseModel):
    id: str
    title: str
    description: str
    difficulty: str | None = None


class ModuleInfo(BaseModel):
    id: str
    title: str
    scenarios: list[ScenarioInfo]


class CatalogResponse(BaseModel):
    modules: list[ModuleInfo]


class StartSessionRequest(BaseModel):
    module: str
    scenario: str


class AssignmentOut(BaseModel):
    title: str
    summary: str
    objectives: list[str] = Field(default_factory=list)


class ObjectiveOut(BaseModel):
    id: str
    description: str
    passed: bool
    detail: str | None = None


class CheckResultOut(BaseModel):
    passed: bool
    objectives: list[ObjectiveOut]


class SessionOut(BaseModel):
    session_id: str
    module: str
    scenario: str
    status: str
    workspace_path: str
    repo_path: str
    assignment: AssignmentOut
    check: CheckResultOut | None = None
    previous_session_id: str | None = None


class DirEntryOut(BaseModel):
    name: str
    path: str
    kind: str  # file | directory | symlink


class FileListOut(BaseModel):
    path: str
    entries: list[DirEntryOut]


class FileContentOut(BaseModel):
    path: str
    content: str
    revision: str
    size: int


class FileWriteRequest(BaseModel):
    path: str
    content: str
    expected_revision: str


class FileWriteOut(BaseModel):
    path: str
    revision: str
    size: int


class TerminalTicketResponse(BaseModel):
    ticket: str
    expires_in: int
    session_id: str
