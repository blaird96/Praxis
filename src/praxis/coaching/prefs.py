"""Non-secret coaching preferences (model choice, enabled flag).

Never stores the API key itself - see `secrets_store.py` for that.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from praxis.paths import coaching_prefs_path, ensure_praxis_home

DEFAULT_MODEL = "gpt-4o-mini"


class CoachingPrefs(BaseModel):
    model: str = DEFAULT_MODEL
    enabled: bool = True


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_coaching_prefs(home: Path | None = None) -> CoachingPrefs:
    path = coaching_prefs_path(home)
    if not path.exists():
        return CoachingPrefs()
    try:
        return CoachingPrefs.model_validate(_read_json(path))
    except (json.JSONDecodeError, ValueError):
        return CoachingPrefs()


def save_coaching_prefs(prefs: CoachingPrefs, home: Path | None = None) -> None:
    root = ensure_praxis_home(home)
    path = coaching_prefs_path(root)
    path.write_text(
        json.dumps(prefs.model_dump(mode="json"), indent=2) + "\n",
        encoding="utf-8",
    )
