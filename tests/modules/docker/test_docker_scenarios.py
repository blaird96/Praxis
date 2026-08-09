"""Docker scenario tests (skipped when Docker is unavailable)."""

from __future__ import annotations

from pathlib import Path

import pytest

from praxis.modules.docker import docker_ops
from praxis.modules.docker.scenarios.dockerfile_basic import (
    REFERENCE_DOCKERFILE,
    DockerfileBasicScenario,
)
from praxis.modules.docker.scenarios.dockerfile_broken import DockerfileBrokenScenario

pytestmark = pytest.mark.skipif(
    not docker_ops.docker_available(),
    reason="docker daemon not available",
)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    workspace = tmp_path / "session1"
    (workspace / ".praxis").mkdir(parents=True)
    path = workspace / "repo"
    path.mkdir()
    return path


def test_dockerfile_basic(repo: Path) -> None:
    scenario = DockerfileBasicScenario()
    state = scenario.setup(repo)
    assert scenario.validate(repo, state).passed is False
    (repo / "Dockerfile").write_text(REFERENCE_DOCKERFILE, encoding="utf-8")
    assert scenario.validate(repo, state).passed


def test_dockerfile_broken(repo: Path) -> None:
    scenario = DockerfileBrokenScenario()
    state = scenario.setup(repo)
    assert scenario.validate(repo, state).passed is False
    (repo / "Dockerfile").write_text(
        "FROM python:3.12-slim\nWORKDIR /app\nCOPY app.py .\n"
        "ENV PORT=8080\nEXPOSE 8080\nCMD [\"python\", \"app.py\"]\n",
        encoding="utf-8",
    )
    assert scenario.validate(repo, state).passed
