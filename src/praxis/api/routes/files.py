"""Exercise repository filesystem endpoints (active session only)."""

from __future__ import annotations

from fastapi import APIRouter, Query

from praxis import runner
from praxis.api import filesystem as fs
from praxis.api.schemas import (
    DirectoryCreateOut,
    DirectoryCreateRequest,
    DirEntryOut,
    FileContentOut,
    FileCreateRequest,
    FileListOut,
    FileWriteOut,
    FileWriteRequest,
)

router = APIRouter(prefix="/session", tags=["files"])


@router.get("/files", response_model=FileListOut)
def list_files(
    path: str = Query(default=".", description="Repository-relative directory path"),
) -> FileListOut:
    session = runner.require_active_session()
    rel = fs.normalize_rel_path(path, allow_root=True)
    entries = fs.list_directory(session, path)
    return FileListOut(
        path=rel or ".",
        entries=[
            DirEntryOut(name=e.name, path=e.path, kind=str(e.kind)) for e in entries
        ],
    )


@router.get("/file", response_model=FileContentOut)
def read_file(
    path: str = Query(..., description="Repository-relative file path"),
) -> FileContentOut:
    session = runner.require_active_session()
    text = fs.read_text_file(session, path)
    return FileContentOut(
        path=text.path,
        content=text.content,
        revision=text.revision,
        size=text.size,
    )


@router.put("/file", response_model=FileWriteOut)
def write_file(body: FileWriteRequest) -> FileWriteOut:
    session = runner.require_active_session()
    result = fs.write_text_file(
        session,
        body.path,
        body.content,
        expected_revision=body.expected_revision,
    )
    return FileWriteOut(path=result.path, revision=result.revision, size=result.size)


@router.post("/file", response_model=FileWriteOut)
def create_file(body: FileCreateRequest) -> FileWriteOut:
    session = runner.require_active_session()
    result = fs.create_text_file(session, body.path, body.content)
    return FileWriteOut(path=result.path, revision=result.revision, size=result.size)


@router.post("/directory", response_model=DirectoryCreateOut)
def create_directory(body: DirectoryCreateRequest) -> DirectoryCreateOut:
    session = runner.require_active_session()
    path = fs.create_directory(session, body.path)
    return DirectoryCreateOut(path=path)
