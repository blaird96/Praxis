"""Tests for durable per-scenario completion tracking."""

from __future__ import annotations

from pathlib import Path

from praxis.progress import load_progress, record_check_result, scenario_completed


def test_record_check_result_creates_entry(praxis_home: Path) -> None:
    entry = record_check_result("git", "merge-conflict", False, home=praxis_home)
    assert entry.attempts == 1
    assert entry.passed is False
    assert entry.first_passed_at is None

    reloaded = load_progress(praxis_home)
    assert "git/merge-conflict" in reloaded.entries


def test_first_pass_timestamp_is_frozen(praxis_home: Path) -> None:
    record_check_result("git", "merge-conflict", False, home=praxis_home)
    first_pass = record_check_result("git", "merge-conflict", True, home=praxis_home)
    assert first_pass.attempts == 2
    assert first_pass.passed is True
    assert first_pass.first_passed_at is not None

    later = record_check_result("git", "merge-conflict", True, home=praxis_home)
    assert later.attempts == 3
    assert later.first_passed_at == first_pass.first_passed_at


def test_scenario_completed_reflects_latest_pass_state(praxis_home: Path) -> None:
    assert scenario_completed("git", "merge-conflict", home=praxis_home) is False

    record_check_result("git", "merge-conflict", True, home=praxis_home)
    assert scenario_completed("git", "merge-conflict", home=praxis_home) is True


def test_completed_reflects_latest_check_but_first_pass_timestamp_is_preserved(
    praxis_home: Path,
) -> None:
    """`completed` tracks the most recent check; `first_passed_at` is a milestone."""
    record_check_result("git", "merge-conflict", True, home=praxis_home)
    record_check_result("git", "merge-conflict", False, home=praxis_home)
    entry = load_progress(praxis_home).entries["git/merge-conflict"]
    assert entry.passed is False
    assert entry.first_passed_at is not None
    assert scenario_completed("git", "merge-conflict", home=praxis_home) is False


def test_entries_are_independent_per_scenario(praxis_home: Path) -> None:
    record_check_result("git", "merge-conflict", True, home=praxis_home)
    record_check_result("docker", "dockerfile-basic", False, home=praxis_home)

    store = load_progress(praxis_home)
    assert store.entries["git/merge-conflict"].passed is True
    assert store.entries["docker/dockerfile-basic"].passed is False


def test_load_progress_missing_file_returns_empty_store(praxis_home: Path) -> None:
    store = load_progress(praxis_home)
    assert store.entries == {}


def test_load_progress_corrupt_file_returns_empty_store(praxis_home: Path) -> None:
    from praxis.paths import ensure_praxis_home, progress_path

    root = ensure_praxis_home(praxis_home)
    progress_path(root).write_text("not json", encoding="utf-8")
    store = load_progress(praxis_home)
    assert store.entries == {}
