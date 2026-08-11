"""Tests for non-secret coaching preferences persistence."""

from __future__ import annotations

from pathlib import Path

from praxis.coaching.prefs import (
    CoachingPrefs,
    load_coaching_prefs,
    save_coaching_prefs,
)


def test_defaults_when_no_file_exists(praxis_home: Path) -> None:
    prefs = load_coaching_prefs(praxis_home)
    assert prefs.model == "gpt-4o-mini"
    assert prefs.enabled is True


def test_round_trip(praxis_home: Path) -> None:
    save_coaching_prefs(CoachingPrefs(model="gpt-4o", enabled=False), praxis_home)
    reloaded = load_coaching_prefs(praxis_home)
    assert reloaded.model == "gpt-4o"
    assert reloaded.enabled is False


def test_corrupt_file_falls_back_to_defaults(praxis_home: Path) -> None:
    from praxis.paths import coaching_prefs_path, ensure_praxis_home

    root = ensure_praxis_home(praxis_home)
    coaching_prefs_path(root).write_text("not json", encoding="utf-8")
    prefs = load_coaching_prefs(praxis_home)
    assert prefs.model == "gpt-4o-mini"


def test_prefs_file_never_contains_api_key(praxis_home: Path) -> None:
    save_coaching_prefs(CoachingPrefs(model="gpt-4o"), praxis_home)
    from praxis.paths import coaching_prefs_path

    raw = coaching_prefs_path(praxis_home).read_text(encoding="utf-8")
    assert "api_key" not in raw
    assert "sk-" not in raw
