"""Tests for lab shell helpers."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from praxis.ui.shell import ShellLaunchError, resolve_shell_command, run_lab_shell


def test_resolve_shell_respects_praxis_shell(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PRAXIS_SHELL", "custom-shell")
    assert resolve_shell_command() == ["custom-shell"]


def test_run_lab_shell_uses_repo_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.setenv("PRAXIS_SHELL", "fake-shell")

    captured: dict[str, object] = {}

    def fake_run(command: list[str], **kwargs: object) -> MagicMock:
        captured["command"] = command
        captured["kwargs"] = kwargs
        result = MagicMock()
        result.returncode = 0
        return result

    monkeypatch.setattr("praxis.ui.shell.subprocess.run", fake_run)
    code = run_lab_shell(repo)
    assert code == 0
    assert captured["command"] == ["fake-shell"]
    assert captured["kwargs"]["cwd"] == str(repo.resolve())
    assert captured["kwargs"]["shell"] is False


def test_run_lab_shell_missing_repo(tmp_path: Path) -> None:
    with pytest.raises(ShellLaunchError, match="does not exist"):
        run_lab_shell(tmp_path / "missing")


def test_run_lab_shell_oserror(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.setenv("PRAXIS_SHELL", "fake-shell")

    def boom(*_args: object, **_kwargs: object) -> object:
        raise OSError("cannot exec")

    monkeypatch.setattr("praxis.ui.shell.subprocess.run", boom)
    with pytest.raises(ShellLaunchError, match="Failed to launch"):
        run_lab_shell(repo)
