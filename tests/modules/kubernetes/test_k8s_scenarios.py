"""Kubernetes scenario smoke tests (skipped without kind/kubectl)."""

from __future__ import annotations

from pathlib import Path

import pytest

from praxis.modules.docker import docker_ops
from praxis.modules.kubernetes import k8s_ops
from praxis.modules.kubernetes.scenarios.all_scenarios import (
    DeployUnavailableScenario,
)

pytestmark = pytest.mark.skipif(
    not (
        docker_ops.docker_available()
        and k8s_ops.kind_available()
        and k8s_ops.kubectl_available()
    ),
    reason="docker/kind/kubectl not available",
)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    workspace = tmp_path / "k8ssession"
    (workspace / ".praxis").mkdir(parents=True)
    path = workspace / "repo"
    path.mkdir()
    return path


def test_deploy_unavailable(repo: Path) -> None:
    scenario = DeployUnavailableScenario()
    state = scenario.setup(repo)
    assert scenario.validate(repo, state).passed is False
    manifest = repo / "manifests" / "web.yaml"
    text = manifest.read_text(encoding="utf-8").replace("replicas: 0", "replicas: 1")
    manifest.write_text(text, encoding="utf-8")
    assert scenario.validate(repo, state).passed
    # cleanup namespace
    k8s_ops._kubectl(  # noqa: SLF001
        "delete", "namespace", state.namespace, "--ignore-not-found", "--wait=false"
    )
