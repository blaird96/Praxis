"""Secure, session-scoped exercise repository filesystem helpers.

Path authority is always the server-resolved active session repo. Clients may only
submit repository-relative paths using ``/`` separators.
"""

from __future__ import annotations

import hashlib
import os
import re
import tempfile
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path, PurePosixPath

from praxis.errors import PraxisError
from praxis.models import Session

# MVP editor limit: keep Monaco/API payloads bounded (configurable constant only).
MAX_EDITOR_BYTES = 1_048_576  # 1 MiB

_DRIVE_PATH = re.compile(r"^[A-Za-z]:")
_GIT_DIR = ".git"


class EntryKind(StrEnum):
    FILE = "file"
    DIRECTORY = "directory"
    SYMLINK = "symlink"


class PathRejectedError(PraxisError):
    """Relative path is invalid or escapes the exercise repository."""


class FileConflictError(PraxisError):
    """Write rejected because expected_revision does not match current content."""


class UnsupportedTextError(PraxisError):
    """File is not supported UTF-8 editor content."""


class EditorFileTooLargeError(PraxisError):
    """File exceeds MAX_EDITOR_BYTES."""


class DirectoryRequiredError(PraxisError):
    """Listing target is not a traversable directory."""


@dataclass(frozen=True, slots=True)
class DirEntry:
    name: str
    path: str  # canonical relative path with /
    kind: EntryKind


@dataclass(frozen=True, slots=True)
class TextFile:
    path: str
    content: str
    revision: str
    size: int


@dataclass(frozen=True, slots=True)
class WriteResult:
    path: str
    revision: str
    size: int


def content_revision(content: str) -> str:
    """Opaque revision derived from UTF-8 file contents (sha-256 hex)."""
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    return digest


def normalize_rel_path(path: str | None, *, allow_root: bool) -> str:
    """Public wrapper for API path validation / normalization."""
    return _canonical_rel(path, allow_root=allow_root)


def _canonical_rel(path: str | None, *, allow_root: bool) -> str:
    """Validate and normalize a client path to a ``/``-separated relative form."""
    if path is None or path == "" or path == ".":
        if allow_root:
            return ""
        raise PathRejectedError("File path is required")

    if "\\" in path or path.startswith("\\\\"):
        raise PathRejectedError("Paths must use '/' separators (not backslash)")

    raw = path.strip()
    if raw != path:
        raise PathRejectedError("Paths must not include surrounding whitespace")

    if raw.startswith("/"):
        raise PathRejectedError("Absolute paths are not allowed")
    if raw.startswith("//"):
        raise PathRejectedError("UNC paths are not allowed")
    if _DRIVE_PATH.match(raw):
        raise PathRejectedError("Drive-qualified paths are not allowed")

    parts = PurePosixPath(raw).parts
    if not parts:
        if allow_root:
            return ""
        raise PathRejectedError("File path is required")

    for part in parts:
        if part in {"", ".", ".."}:
            raise PathRejectedError(f"Invalid path component: {part!r}")
        if part == _GIT_DIR:
            raise PathRejectedError("Access to .git is not allowed")

    return "/".join(parts)


def _repo_root(session: Session) -> Path:
    return Path(session.repo_path).resolve()


def _resolve_under_repo(session: Session, rel: str) -> tuple[Path, Path]:
    """Return (repo_root, target) with containment checks.

    Does not require the target to exist. Raises if the resolved path escapes
    the repo (including via symlink resolution).
    """
    repo = _repo_root(session)
    if rel == "":
        target = repo
    else:
        # Build without resolving intermediate client tricks; resolve at the end.
        target = (repo / Path(*rel.split("/"))).resolve()

    try:
        target.relative_to(repo)
    except ValueError as exc:
        raise PathRejectedError("Path escapes the exercise repository") from exc
    return repo, target


def _reject_if_symlink(path: Path, *, label: str) -> None:
    if path.exists() and path.is_symlink():
        raise PathRejectedError(f"Symlink {label} is not accessible via the editor")


def _ensure_parents_not_symlink(repo: Path, target: Path) -> None:
    """Refuse paths whose ancestors (under repo) are symlinks."""
    try:
        rel = target.relative_to(repo)
    except ValueError as exc:
        raise PathRejectedError("Path escapes the exercise repository") from exc
    current = repo
    for part in rel.parts:
        current = current / part
        if current.exists() and current.is_symlink():
            raise PathRejectedError("Symlink traversal is not allowed")


def list_directory(session: Session, path: str | None = ".") -> list[DirEntry]:
    """List a single directory under the exercise repo (non-recursive)."""
    rel = _canonical_rel(path, allow_root=True)
    repo, target = _resolve_under_repo(session, rel)
    _ensure_parents_not_symlink(repo, target)
    _reject_if_symlink(target, label="directories")

    if not target.exists():
        raise FileNotFoundError(f"File not found: {rel or '.'}")
    if not target.is_dir():
        raise DirectoryRequiredError(f"Not a directory: {rel or '.'}")

    entries: list[DirEntry] = []
    for child in target.iterdir():
        name = child.name
        if name == _GIT_DIR:
            continue
        child_rel = name if rel == "" else f"{rel}/{name}"
        if child.is_symlink():
            kind = EntryKind.SYMLINK
        elif child.is_dir():
            kind = EntryKind.DIRECTORY
        elif child.is_file():
            kind = EntryKind.FILE
        else:
            continue
        entries.append(DirEntry(name=name, path=child_rel, kind=kind))

    def sort_key(entry: DirEntry) -> tuple[int, str]:
        if entry.kind == EntryKind.DIRECTORY:
            rank = 0
        elif entry.kind == EntryKind.FILE:
            rank = 1
        else:
            rank = 2
        return (rank, entry.name.lower())

    entries.sort(key=sort_key)
    return entries


def _decode_text(data: bytes, *, rel: str) -> str:
    if b"\x00" in data:
        raise UnsupportedTextError(
            f"{rel} looks like a binary file and cannot be opened in the text editor"
        )
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise UnsupportedTextError(
            f"{rel} is not valid UTF-8 text and cannot be opened in the text editor"
        ) from exc


def read_text_file(session: Session, path: str) -> TextFile:
    """Read a UTF-8 text file within the exercise repo."""
    rel = _canonical_rel(path, allow_root=False)
    repo, target = _resolve_under_repo(session, rel)
    _ensure_parents_not_symlink(repo, target)
    _reject_if_symlink(target, label="files")

    if not target.exists():
        raise FileNotFoundError(f"File not found: {rel}")
    if not target.is_file():
        raise PathRejectedError(f"Not a regular file: {rel}")

    size = target.stat().st_size
    if size > MAX_EDITOR_BYTES:
        raise EditorFileTooLargeError(
            f"{rel} is {size} bytes; editor limit is {MAX_EDITOR_BYTES} bytes"
        )

    data = target.read_bytes()
    content = _decode_text(data, rel=rel)
    return TextFile(
        path=rel,
        content=content,
        revision=content_revision(content),
        size=len(data),
    )


def write_text_file(
    session: Session,
    path: str,
    content: str,
    *,
    expected_revision: str,
) -> WriteResult:
    """Atomically write UTF-8 text if ``expected_revision`` matches current content."""
    rel = _canonical_rel(path, allow_root=False)
    repo, target = _resolve_under_repo(session, rel)
    _ensure_parents_not_symlink(repo, target)
    _reject_if_symlink(target, label="files")

    if not target.exists():
        raise FileNotFoundError(f"File not found: {rel}")
    if not target.is_file():
        raise PathRejectedError(f"Not a regular file: {rel}")

    encoded = content.encode("utf-8")
    if len(encoded) > MAX_EDITOR_BYTES:
        raise EditorFileTooLargeError(
            f"Content is {len(encoded)} bytes; editor limit is {MAX_EDITOR_BYTES} bytes"
        )

    current = read_text_file(session, rel)
    if current.revision != expected_revision:
        raise FileConflictError(
            f"{rel} changed since it was loaded. Reload the file before saving."
        )

    mode = target.stat().st_mode
    directory = target.parent
    fd, tmp_name = tempfile.mkstemp(
        prefix=".praxis-edit-",
        suffix=".tmp",
        dir=str(directory),
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, target)
        os.chmod(target, mode)
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        raise

    new_revision = content_revision(content)
    return WriteResult(path=rel, revision=new_revision, size=len(encoded))
