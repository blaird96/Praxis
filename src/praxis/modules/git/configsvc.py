"""Small configsvc repository theme shared by Git training scenarios.

Plain helpers only — not a scenario framework.
"""

from __future__ import annotations

from pathlib import Path

from praxis.modules.git import git_ops

APP_PY = "app.py"
SETTINGS_TOML = "settings.toml"
README_MD = "README.md"
TEST_APP = "tests/test_app.py"

BASE_APP_PY = '''\
"""Minimal settings service for Praxis labs."""

from pathlib import Path

DEFAULT_TIMEOUT_MS = 1000


def load_settings(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"')
    return values


def timeout_ms(settings: dict[str, str]) -> int:
    raw = settings.get("timeout_ms", str(DEFAULT_TIMEOUT_MS))
    return int(raw)
'''

BASE_SETTINGS_TOML = """\
# configsvc settings
timeout_ms = 1000
log_level = "info"
"""

BASE_README = """\
# configsvc

Tiny settings helper used by Praxis Git labs.
"""

BASE_TEST_APP = '''\
from pathlib import Path

from app import load_settings, timeout_ms


def test_timeout_default(tmp_path: Path) -> None:
    path = tmp_path / "settings.toml"
    path.write_text('timeout_ms = 1000\\n', encoding="utf-8")
    assert timeout_ms(load_settings(path)) == 1000
'''


def hooks_path_for_repo(repo_path: Path) -> Path:
    """Praxis-controlled hooks dir: sibling ``.praxis/hooks`` outside the repo."""
    return repo_path.resolve().parent / ".praxis" / "hooks"


def write_text(repo_path: Path, relative: str, content: str) -> None:
    path = repo_path / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content.encode("utf-8"))


def read_text_normalized(repo_path: Path, relative: str) -> str:
    raw = (repo_path / relative).read_bytes().decode("utf-8")
    return raw.replace("\r\n", "\n").replace("\r", "\n")


def seed_configsvc_files(repo_path: Path) -> None:
    """Write the baseline configsvc tree (no git operations)."""
    write_text(repo_path, APP_PY, BASE_APP_PY)
    write_text(repo_path, SETTINGS_TOML, BASE_SETTINGS_TOML)
    write_text(repo_path, README_MD, BASE_README)
    write_text(repo_path, TEST_APP, BASE_TEST_APP)


def init_configsvc_repo(repo_path: Path, *, commit_message: str = "Initial configsvc") -> str:
    """Initialize a lab repo, seed configsvc, and create the first commit.

    Returns the initial commit SHA.
    """
    git_ops.init(repo_path)
    git_ops.configure_lab_repo(repo_path, hooks_path=hooks_path_for_repo(repo_path))
    seed_configsvc_files(repo_path)
    git_ops.add_all(repo_path)
    return git_ops.commit(repo_path, commit_message)


def show_file_at(repo_path: Path, ref: str, relative: str) -> str | None:
    """Return normalized file content at ``ref:relative``, or None if missing."""
    from praxis.errors import ProcessError

    try:
        text = git_ops.show(repo_path, f"{ref}:{relative}")
    except ProcessError:
        return None
    return text.replace("\r\n", "\n").replace("\r", "\n")
