"""Tests for hybrid session discovery and activation."""

from __future__ import annotations

from pathlib import Path

import pytest

from praxis.errors import SessionNotFoundError
from praxis.models import SessionStatus
from praxis.paths import state_path
from praxis.session import (
    abandon_provisional_session,
    activate_session,
    begin_session,
    load_global_state,
    resolve_session,
)


def test_resolve_from_cwd_inside_repo(praxis_home: Path) -> None:
    session = begin_session(module="git", scenario="merge-conflict", home=praxis_home)
    activate_session(session, scenario_state={"base_sha": "abc"}, home=praxis_home)

    resolved = resolve_session(cwd=session.repo_path, home=praxis_home)
    assert resolved.source == "cwd"
    assert resolved.is_active is True
    assert resolved.session.session_id == session.session_id


def test_resolve_from_workspace_root(praxis_home: Path) -> None:
    session = begin_session(module="git", scenario="merge-conflict", home=praxis_home)
    activate_session(session, home=praxis_home)

    resolved = resolve_session(cwd=session.workspace_path, home=praxis_home)
    assert resolved.source == "cwd"
    assert resolved.session.session_id == session.session_id


def test_resolve_falls_back_to_active(praxis_home: Path, tmp_path: Path) -> None:
    session = begin_session(module="git", scenario="merge-conflict", home=praxis_home)
    activate_session(session, home=praxis_home)

    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    resolved = resolve_session(cwd=elsewhere, home=praxis_home)
    assert resolved.source == "active"
    assert resolved.is_active is True
    assert resolved.session.session_id == session.session_id


def test_resolve_prefers_cwd_over_active(praxis_home: Path) -> None:
    first = begin_session(module="git", scenario="merge-conflict", home=praxis_home)
    activate_session(first, home=praxis_home)

    second = begin_session(module="git", scenario="merge-conflict", home=praxis_home)
    activate_session(second, home=praxis_home)

    # cwd inside first (retained) workspace should win over active=second
    resolved = resolve_session(cwd=first.repo_path, home=praxis_home)
    assert resolved.source == "cwd"
    assert resolved.session.session_id == first.session_id
    assert resolved.is_active is False

    active = resolve_session(cwd=praxis_home, home=praxis_home)
    assert active.source == "active"
    assert active.session.session_id == second.session_id


def test_resolve_error_when_neither(praxis_home: Path, tmp_path: Path) -> None:
    elsewhere = tmp_path / "nowhere"
    elsewhere.mkdir()
    with pytest.raises(SessionNotFoundError, match="No active Praxis session"):
        resolve_session(cwd=elsewhere, home=praxis_home)


def test_activate_sets_global_pointer(praxis_home: Path) -> None:
    session = begin_session(module="git", scenario="merge-conflict", home=praxis_home)
    assert load_global_state(praxis_home).active_session_id is None

    activate_session(session, scenario_state={"main_tip_sha": "1"}, home=praxis_home)
    assert load_global_state(praxis_home).active_session_id == session.session_id
    assert session.status == SessionStatus.ACTIVE
    assert state_path(praxis_home).is_file()


def test_abandon_leaves_active_unchanged(praxis_home: Path) -> None:
    keeper = begin_session(module="git", scenario="merge-conflict", home=praxis_home)
    activate_session(keeper, home=praxis_home)

    failed = begin_session(module="git", scenario="merge-conflict", home=praxis_home)
    failed_path = Path(failed.workspace_path)
    abandon_provisional_session(failed, home=praxis_home)

    assert not failed_path.exists()
    assert load_global_state(praxis_home).active_session_id == keeper.session_id
