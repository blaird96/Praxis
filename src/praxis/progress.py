"""Durable per-scenario completion tracking (local, single-user).

Records whether a scenario has ever been passed via ``praxis check``/the API,
independent of any specific session or workspace (which are disposable).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field

from praxis.paths import ensure_praxis_home, progress_path


def _entry_key(module: str, scenario: str) -> str:
    return f"{module}/{scenario}"


class ScenarioProgress(BaseModel):
    attempts: int = 0
    passed: bool = False
    first_passed_at: datetime | None = None
    last_checked_at: datetime


class ProgressStore(BaseModel):
    entries: dict[str, ScenarioProgress] = Field(default_factory=dict)


def load_progress(home: Path | None = None) -> ProgressStore:
    path = progress_path(home)
    if not path.exists():
        return ProgressStore()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return ProgressStore.model_validate(raw)
    except (json.JSONDecodeError, ValueError):
        # Corrupt or unreadable progress data should never block check/catalog.
        return ProgressStore()


def save_progress(store: ProgressStore, home: Path | None = None) -> None:
    root = ensure_praxis_home(home)
    path = progress_path(root)
    path.write_text(
        json.dumps(store.model_dump(mode="json"), indent=2) + "\n",
        encoding="utf-8",
    )


def record_check_result(
    module: str,
    scenario: str,
    passed: bool,
    *,
    home: Path | None = None,
) -> ScenarioProgress:
    """Upsert the progress entry for a scenario after a check completes."""
    store = load_progress(home)
    key = _entry_key(module, scenario)
    now = datetime.now(UTC)
    existing = store.entries.get(key)

    if existing is None:
        entry = ScenarioProgress(
            attempts=1,
            passed=passed,
            first_passed_at=now if passed else None,
            last_checked_at=now,
        )
    else:
        entry = existing.model_copy(
            update={
                "attempts": existing.attempts + 1,
                "passed": passed,
                "first_passed_at": existing.first_passed_at
                or (now if passed else None),
                "last_checked_at": now,
            }
        )

    store.entries[key] = entry
    save_progress(store, home)
    return entry


def scenario_completed(
    module: str,
    scenario: str,
    store: ProgressStore | None = None,
    *,
    home: Path | None = None,
) -> bool:
    """Whether a scenario has ever been passed."""
    store = store if store is not None else load_progress(home)
    entry = store.entries.get(_entry_key(module, scenario))
    return entry is not None and entry.passed
