"""Kubernetes training helpers (kind + kubectl)."""

from __future__ import annotations

import shutil
from pathlib import Path

from praxis.errors import ScenarioSetupError
from praxis.process import ProcessResult, run

PRAXIS_CLUSTER = "praxis-lab"


def kubectl_available() -> bool:
    return shutil.which("kubectl") is not None


def kind_available() -> bool:
    return shutil.which("kind") is not None


def require_k8s_tools() -> None:
    missing = []
    if not kubectl_available():
        missing.append("kubectl")
    if not kind_available():
        missing.append("kind")
    if missing:
        raise ScenarioSetupError(
            "Kubernetes labs require "
            + ", ".join(missing)
            + " on PATH (and Docker for kind nodes). Install the missing tools and retry."
        )


def _kubectl(
    *args: str,
    allowed_returncodes: set[int] | None = None,
) -> ProcessResult:
    require_k8s_tools()
    return run(
        ["kubectl", *args],
        allowed_returncodes=allowed_returncodes,
    )


def _kind(
    *args: str,
    allowed_returncodes: set[int] | None = None,
) -> ProcessResult:
    require_k8s_tools()
    return run(["kind", *args], allowed_returncodes=allowed_returncodes)


def ensure_cluster() -> None:
    """Create the shared Praxis kind cluster if missing."""
    require_k8s_tools()
    result = _kind("get", "clusters", allowed_returncodes={0, 1})
    clusters = {line.strip() for line in result.stdout.splitlines() if line.strip()}
    if PRAXIS_CLUSTER not in clusters:
        _kind("create", "cluster", "--name", PRAXIS_CLUSTER)


def namespace_for(repo_path: Path) -> str:
    session = repo_path.resolve().parent.name
    safe = "".join(ch if ch.isalnum() else "-" for ch in session).lower()[:40]
    return f"praxis-{safe}"


def reset_namespace(namespace: str) -> None:
    ensure_cluster()
    _kubectl(
        "delete",
        "namespace",
        namespace,
        "--ignore-not-found",
        "--wait=true",
        allowed_returncodes={0, 1},
    )
    _kubectl("create", "namespace", namespace)


def apply_manifest(namespace: str, path: Path) -> None:
    _kubectl("apply", "-n", namespace, "-f", str(path))


def get_json(namespace: str, resource: str, name: str) -> str:
    result = _kubectl(
        "get",
        resource,
        name,
        "-n",
        namespace,
        "-o",
        "json",
        allowed_returncodes={0, 1},
    )
    return result.stdout if result.returncode == 0 else ""


def deployment_available(namespace: str, name: str) -> bool:
    result = _kubectl(
        "get",
        "deploy",
        name,
        "-n",
        namespace,
        "-o",
        "jsonpath={.status.availableReplicas}",
        allowed_returncodes={0, 1},
    )
    if result.returncode != 0:
        return False
    raw = result.stdout.strip()
    return raw.isdigit() and int(raw) > 0


def endpoints_ready(namespace: str, service: str) -> bool:
    result = _kubectl(
        "get",
        "endpoints",
        service,
        "-n",
        namespace,
        "-o",
        "jsonpath={.subsets[*].addresses[*].ip}",
        allowed_returncodes={0, 1},
    )
    return bool(result.stdout.strip())


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
