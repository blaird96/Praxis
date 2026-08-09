"""Thin docker argv helpers built on ``praxis.process.run``."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from praxis.errors import ProcessError, ScenarioSetupError
from praxis.process import ProcessResult, run


def docker_available() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        result = run(
            ["docker", "info"],
            allowed_returncodes={0, 1},
        )
    except Exception:
        return False
    return result.returncode == 0


def require_docker() -> None:
    if not docker_available():
        raise ScenarioSetupError(
            "Docker is required for this scenario but the Docker CLI/daemon "
            "is not available. Install Docker Desktop or Engine, start the "
            "daemon, and retry."
        )


def _docker(
    *args: str,
    cwd: Path | None = None,
    allowed_returncodes: set[int] | None = None,
) -> ProcessResult:
    require_docker()
    return run(
        ["docker", *args],
        cwd=cwd,
        allowed_returncodes=allowed_returncodes,
    )


def cleanup_prefix(prefix: str) -> None:
    """Remove containers and images whose names/tags start with ``prefix``."""
    require_docker()
    ps = _docker(
        "ps", "-a", "--filter", f"name={prefix}", "--format", "{{.ID}}"
    )
    for cid in ps.stdout.splitlines():
        cid = cid.strip()
        if cid:
            _docker("rm", "-f", cid, allowed_returncodes={0, 1})
    images = _docker("images", "--format", "{{.Repository}}:{{.Tag}} {{.ID}}")
    for line in images.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        ref, _, image_id = line.partition(" ")
        if ref.startswith(prefix) or prefix in ref:
            _docker("rmi", "-f", image_id.strip(), allowed_returncodes={0, 1})


def build(tag: str, context: Path, *, dockerfile: str = "Dockerfile") -> None:
    _docker("build", "-t", tag, "-f", dockerfile, ".", cwd=context)


def run_detached(
    name: str,
    image: str,
    *,
    publish: list[str] | None = None,
    env: dict[str, str] | None = None,
    volumes: list[str] | None = None,
    user: str | None = None,
) -> str:
    args = ["run", "-d", "--name", name]
    for mapping in publish or []:
        args.extend(["-p", mapping])
    for key, value in (env or {}).items():
        args.extend(["-e", f"{key}={value}"])
    for vol in volumes or []:
        args.extend(["-v", vol])
    if user:
        args.extend(["--user", user])
    args.append(image)
    result = _docker(*args)
    return result.stdout.strip()


def stop_rm(name: str) -> None:
    _docker("rm", "-f", name, allowed_returncodes={0, 1})


def inspect(name_or_id: str) -> dict:
    result = _docker("inspect", name_or_id)
    data = json.loads(result.stdout)
    if not data:
        raise ProcessError(f"docker inspect returned empty for {name_or_id}")
    return data[0]


def exec_run(name: str, *command: str) -> ProcessResult:
    return _docker("exec", name, *command, allowed_returncodes={0, 1})


def image_has_file(image: str, path: str) -> bool:
    result = _docker(
        "run",
        "--rm",
        "--entrypoint",
        "sh",
        image,
        "-c",
        f"test -e {path}",
        allowed_returncodes={0, 1},
    )
    return result.returncode == 0


def http_ok(url: str, *, timeout_seconds: int = 5) -> bool:
    """Best-effort HTTP check via python urllib (no extra deps)."""
    import urllib.error
    import urllib.request

    try:
        with urllib.request.urlopen(url, timeout=timeout_seconds) as resp:
            return 200 <= getattr(resp, "status", 200) < 300
    except (urllib.error.URLError, TimeoutError, OSError):
        return False
