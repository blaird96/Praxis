"""Shared pytest fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def praxis_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point PRAXIS_HOME at an isolated temporary directory."""
    home = tmp_path / "praxis-home"
    home.mkdir()
    monkeypatch.setenv("PRAXIS_HOME", str(home))
    return home.resolve()
