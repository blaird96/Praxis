"""Host-tool availability checks for training modules."""

from __future__ import annotations


def module_availability(module_id: str) -> tuple[bool, str | None]:
    """Return ``(available, reason)`` for starting scenarios in ``module_id``.

    ``reason`` is set only when unavailable.
    """
    if module_id == "git":
        return True, None

    if module_id == "docker":
        from praxis.modules.docker.docker_ops import docker_available

        if docker_available():
            return True, None
        return (
            False,
            "Docker CLI/daemon is not available. Install and start Docker Desktop "
            "or Engine, then restart Praxis.",
        )

    if module_id == "kubernetes":
        from praxis.modules.docker.docker_ops import docker_available
        from praxis.modules.kubernetes import k8s_ops

        missing: list[str] = []
        if not docker_available():
            missing.append("Docker")
        if not k8s_ops.kind_available():
            missing.append("kind")
        if not k8s_ops.kubectl_available():
            missing.append("kubectl")
        if not missing:
            return True, None
        return (
            False,
            "Kubernetes labs require "
            + ", ".join(missing)
            + " on PATH (kind needs a working Docker daemon). "
            "Install the missing tools, then restart Praxis.",
        )

    return True, None
