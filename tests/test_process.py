"""Tests for safe subprocess execution."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from praxis.errors import ProcessError
from praxis.process import run


def test_run_success_captures_stdout() -> None:
    result = run([sys.executable, "-c", "print('hello')"])
    assert result.returncode == 0
    assert result.stdout.strip() == "hello"
    assert result.stderr == ""


def test_run_rejects_nonzero_by_default() -> None:
    with pytest.raises(ProcessError) as exc_info:
        run([sys.executable, "-c", "raise SystemExit(7)"])
    assert exc_info.value.returncode == 7
    assert exc_info.value.argv[0] == sys.executable


def test_run_allows_configured_nonzero() -> None:
    result = run(
        [sys.executable, "-c", "raise SystemExit(1)"],
        allowed_returncodes={0, 1},
    )
    assert result.returncode == 1


def test_run_respects_cwd(tmp_path: Path) -> None:
    marker = tmp_path / "marker.txt"
    marker.write_text("ok", encoding="utf-8")
    result = run(
        [
            sys.executable,
            "-c",
            "import pathlib; print(pathlib.Path('marker.txt').read_text())",
        ],
        cwd=tmp_path,
    )
    assert result.stdout.strip() == "ok"


def test_run_timeout() -> None:
    with pytest.raises(ProcessError, match="timed out"):
        run(
            [sys.executable, "-c", "import time; time.sleep(5)"],
            timeout=0.2,
        )


def test_run_empty_argv() -> None:
    with pytest.raises(ProcessError, match="empty argv"):
        run([])


def test_run_missing_executable() -> None:
    with pytest.raises(ProcessError, match="not found"):
        run(["praxis-definitely-missing-binary-xyz"])


def test_run_does_not_use_shell(monkeypatch: pytest.MonkeyPatch) -> None:
    import subprocess

    captured: dict[str, object] = {}

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured["args"] = args
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(
            args=args[0],
            returncode=0,
            stdout="",
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    run([sys.executable, "-c", "pass"])
    assert captured["kwargs"]["shell"] is False
    assert isinstance(captured["args"][0], list)
