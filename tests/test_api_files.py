"""Filesystem API tests for the active-session exercise repository."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from praxis import runner
from praxis.api.app import create_app
from praxis.api.filesystem import MAX_EDITOR_BYTES, content_revision
from praxis.api.security import TOKEN_HEADER, AppSecurity
from praxis.registry import bootstrap_registry, clear_registry


@pytest.fixture(autouse=True)
def _registry(praxis_home: Path) -> None:
    clear_registry()
    bootstrap_registry()
    yield
    clear_registry()


@pytest.fixture
def security() -> AppSecurity:
    return AppSecurity.create(
        host="127.0.0.1",
        port=8765,
        token="test-capability-token",
        extra_origins=["http://127.0.0.1:5173"],
    )


@pytest.fixture
def client(security: AppSecurity) -> TestClient:
    app = create_app(security=security, allow_vite_origins=False)
    return TestClient(app)


@pytest.fixture
def started(client: TestClient, security: AppSecurity, praxis_home: Path) -> dict:
    runner.start("git", "merge-conflict", home=praxis_home)
    session = client.get("/api/session", headers=_auth(security)).json()
    return session


def _auth(security: AppSecurity) -> dict[str, str]:
    return {
        TOKEN_HEADER: security.token,
        "Host": "127.0.0.1:8765",
    }


def test_list_root_excludes_git(
    client: TestClient, security: AppSecurity, started: dict
) -> None:
    response = client.get("/api/session/files", headers=_auth(security))
    assert response.status_code == 200
    body = response.json()
    assert body["path"] == "."
    names = [e["name"] for e in body["entries"]]
    assert "greeting.txt" in names
    assert ".git" not in names
    kinds = {e["name"]: e["kind"] for e in body["entries"]}
    assert kinds["greeting.txt"] == "file"


def test_list_nested_directory(
    client: TestClient, security: AppSecurity, started: dict, praxis_home: Path
) -> None:
    repo = Path(started["repo_path"])
    nested = repo / "docs" / "notes"
    nested.mkdir(parents=True)
    (nested / "readme.txt").write_text("hello", encoding="utf-8")

    parent = client.get(
        "/api/session/files",
        headers=_auth(security),
        params={"path": "docs"},
    )
    assert parent.status_code == 200
    assert {e["name"] for e in parent.json()["entries"]} == {"notes"}
    assert parent.json()["entries"][0]["kind"] == "directory"
    assert parent.json()["entries"][0]["path"] == "docs/notes"

    child = client.get(
        "/api/session/files",
        headers=_auth(security),
        params={"path": "docs/notes"},
    )
    assert child.status_code == 200
    assert child.json()["entries"][0]["path"] == "docs/notes/readme.txt"


def test_read_and_save_with_revision(
    client: TestClient, security: AppSecurity, started: dict
) -> None:
    read = client.get(
        "/api/session/file",
        headers=_auth(security),
        params={"path": "greeting.txt"},
    )
    assert read.status_code == 200
    payload = read.json()
    assert "<<<<<<<" in payload["content"] or "Hello" in payload["content"]
    assert payload["revision"] == content_revision(payload["content"])

    new_content = "Hello from Praxis\n"
    saved = client.put(
        "/api/session/file",
        headers=_auth(security),
        json={
            "path": "greeting.txt",
            "content": new_content,
            "expected_revision": payload["revision"],
        },
    )
    assert saved.status_code == 200
    assert saved.json()["revision"] == content_revision(new_content)
    assert saved.json()["revision"] != payload["revision"]

    again = client.get(
        "/api/session/file",
        headers=_auth(security),
        params={"path": "greeting.txt"},
    )
    assert again.json()["content"] == new_content


def test_stale_revision_rejected(
    client: TestClient, security: AppSecurity, started: dict
) -> None:
    read = client.get(
        "/api/session/file",
        headers=_auth(security),
        params={"path": "greeting.txt"},
    ).json()
    conflict = client.put(
        "/api/session/file",
        headers=_auth(security),
        json={
            "path": "greeting.txt",
            "content": "stale write\n",
            "expected_revision": "not-the-real-revision",
        },
    )
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "file_conflict"
    # Original revision still valid for a correct save
    ok = client.put(
        "/api/session/file",
        headers=_auth(security),
        json={
            "path": "greeting.txt",
            "content": "ok\n",
            "expected_revision": read["revision"],
        },
    )
    assert ok.status_code == 200


@pytest.mark.parametrize(
    "bad_path",
    [
        "../outside.txt",
        "foo/../../etc/passwd",
        "/etc/passwd",
        "C:/Windows/System32",
        "C:\\Windows\\System32",
        "//server/share/file",
        "\\\\server\\share\\file",
        ".git/config",
        "foo/.git/HEAD",
    ],
)
def test_path_tricks_rejected(
    client: TestClient, security: AppSecurity, started: dict, bad_path: str
) -> None:
    response = client.get(
        "/api/session/file",
        headers=_auth(security),
        params={"path": bad_path},
    )
    assert response.status_code == 400
    assert response.json()["code"] == "path_rejected"


def test_symlink_file_and_traversal_rejected(
    client: TestClient, security: AppSecurity, started: dict, tmp_path: Path
) -> None:
    repo = Path(started["repo_path"])
    outside = tmp_path / "secret.txt"
    outside.write_text("secret", encoding="utf-8")
    link = repo / "escape.txt"
    try:
        link.symlink_to(outside)
    except OSError as exc:
        pytest.skip(f"symlinks unavailable: {exc}")

    read = client.get(
        "/api/session/file",
        headers=_auth(security),
        params={"path": "escape.txt"},
    )
    assert read.status_code == 400
    assert read.json()["code"] == "path_rejected"

    listed = client.get("/api/session/files", headers=_auth(security)).json()
    by_name = {e["name"]: e for e in listed["entries"]}
    assert by_name["escape.txt"]["kind"] == "symlink"

    # Directory symlink must not be listable
    outside_dir = tmp_path / "outside_dir"
    outside_dir.mkdir()
    (outside_dir / "x.txt").write_text("x", encoding="utf-8")
    dir_link = repo / "linked-dir"
    try:
        dir_link.symlink_to(outside_dir, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"dir symlinks unavailable: {exc}")

    listing = client.get(
        "/api/session/files",
        headers=_auth(security),
        params={"path": "linked-dir"},
    )
    assert listing.status_code == 400
    assert listing.json()["code"] == "path_rejected"


def test_binary_and_oversized_rejected(
    client: TestClient, security: AppSecurity, started: dict
) -> None:
    repo = Path(started["repo_path"])
    binary = repo / "blob.bin"
    binary.write_bytes(b"hello\x00world")
    oversized = repo / "huge.txt"
    oversized.write_bytes(b"a" * (MAX_EDITOR_BYTES + 1))

    bin_resp = client.get(
        "/api/session/file",
        headers=_auth(security),
        params={"path": "blob.bin"},
    )
    assert bin_resp.status_code == 415
    assert bin_resp.json()["code"] == "unsupported_text"

    big_resp = client.get(
        "/api/session/file",
        headers=_auth(security),
        params={"path": "huge.txt"},
    )
    assert big_resp.status_code == 413
    assert big_resp.json()["code"] == "file_too_large"


def test_files_require_active_session_and_security(
    client: TestClient, security: AppSecurity
) -> None:
    missing = client.get("/api/session/files", headers=_auth(security))
    assert missing.status_code == 404

    runner.start("git", "merge-conflict")

    no_token = client.get(
        "/api/session/files",
        headers={"Host": "127.0.0.1:8765"},
    )
    assert no_token.status_code == 401

    bad_host = client.get(
        "/api/session/files",
        headers={TOKEN_HEADER: security.token, "Host": "evil:8765"},
    )
    assert bad_host.status_code == 400

    bad_origin = client.get(
        "/api/session/files",
        headers={**_auth(security), "Origin": "http://evil.example"},
    )
    assert bad_origin.status_code == 403


def test_reset_invalidates_old_revision(
    client: TestClient, security: AppSecurity, started: dict
) -> None:
    before = client.get(
        "/api/session/file",
        headers=_auth(security),
        params={"path": "greeting.txt"},
    ).json()
    old_revision = before["revision"]

    # Mutate then reset
    client.put(
        "/api/session/file",
        headers=_auth(security),
        json={
            "path": "greeting.txt",
            "content": "mutated before reset\n",
            "expected_revision": old_revision,
        },
    )
    after_mutate = client.get(
        "/api/session/file",
        headers=_auth(security),
        params={"path": "greeting.txt"},
    ).json()

    reset = client.post("/api/session/reset", headers=_auth(security))
    assert reset.status_code == 200
    assert reset.json()["check"] is not None

    stale = client.put(
        "/api/session/file",
        headers=_auth(security),
        json={
            "path": "greeting.txt",
            "content": "should fail\n",
            "expected_revision": after_mutate["revision"],
        },
    )
    assert stale.status_code == 409

    fresh = client.get(
        "/api/session/file",
        headers=_auth(security),
        params={"path": "greeting.txt"},
    ).json()
    assert fresh["revision"] != after_mutate["revision"]
    assert "mutated before reset" not in fresh["content"]
