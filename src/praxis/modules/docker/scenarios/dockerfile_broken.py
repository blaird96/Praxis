"""Docker dockerfile-broken scenario."""

from __future__ import annotations

import time
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from praxis.errors import ScenarioSetupError
from praxis.models import Assignment, CheckResult, ObjectiveResult
from praxis.modules.docker import docker_ops
from praxis.modules.docker.lab_app import resource_prefix, write_app

BROKEN_DOCKERFILE = """\
FROM python:3.12-slim
WORKDIR /app
COPY missing_app.py .
ENV PORT=8080
EXPOSE 8080
CMD ["python", "app.py"]
"""


class DockerfileBrokenState(BaseModel):
    model_config = ConfigDict(frozen=True)

    image_tag: str
    container_name: str
    host_port: int
    prefix: str


class DockerfileBrokenScenario:
    id: str = "dockerfile-broken"
    module: str = "docker"
    title: str = "Fix a broken Dockerfile"
    description: str = (
        "The provided Dockerfile fails to build. Fix COPY/paths so the app image builds and runs."
    )
    difficulty: str | None = "beginner"
    concepts: list[str] = ["dockerfile", "build-context", "COPY"]
    state_model: type[DockerfileBrokenState] = DockerfileBrokenState

    def assignment(self) -> Assignment:
        return Assignment(
            title=self.title,
            summary=(
                "A Dockerfile is present but broken (it copies a missing file). "
                "Fix it so `app.py` is copied correctly, the image builds, and "
                "the app responds on port 8080."
            ),
            objectives=[
                "Dockerfile builds successfully.",
                "Container serves HTTP 200 on the published port.",
            ],
        )

    def setup(self, repo_path: Path) -> DockerfileBrokenState:
        docker_ops.require_docker()
        prefix = resource_prefix(repo_path)
        docker_ops.cleanup_prefix(prefix)
        write_app(repo_path)
        (repo_path / "Dockerfile").write_text(BROKEN_DOCKERFILE, encoding="utf-8")
        host_port = 18100 + (abs(hash(prefix)) % 800)
        state = DockerfileBrokenState(
            image_tag=f"{prefix}-fix:lab",
            container_name=f"{prefix}-fix",
            host_port=host_port,
            prefix=prefix,
        )
        self._verify_setup(repo_path, state)
        return state

    def _verify_setup(
        self, repo_path: Path, state: DockerfileBrokenState
    ) -> None:
        if not (repo_path / "Dockerfile").is_file():
            raise ScenarioSetupError("Dockerfile missing")
        # Confirm build currently fails
        try:
            docker_ops.build(state.image_tag, repo_path)
        except Exception:
            return
        raise ScenarioSetupError("Expected initial Dockerfile build to fail")

    def validate(
        self, repo_path: Path, state: DockerfileBrokenState
    ) -> CheckResult:
        docker_ops.cleanup_prefix(state.prefix)
        build_ok = True
        detail = None
        try:
            docker_ops.build(state.image_tag, repo_path)
        except Exception as exc:  # noqa: BLE001
            build_ok = False
            detail = str(exc)
        objectives = [
            ObjectiveResult(
                id="image-builds",
                description="Fixed Dockerfile builds",
                passed=build_ok,
                detail=detail,
            )
        ]
        http_ok = False
        http_detail = None
        if build_ok:
            try:
                docker_ops.stop_rm(state.container_name)
                docker_ops.run_detached(
                    state.container_name,
                    state.image_tag,
                    publish=[f"{state.host_port}:8080"],
                )
                for _ in range(20):
                    if docker_ops.http_ok(f"http://127.0.0.1:{state.host_port}/"):
                        http_ok = True
                        break
                    time.sleep(0.25)
                if not http_ok:
                    http_detail = "no HTTP 200"
            except Exception as exc:  # noqa: BLE001
                http_detail = str(exc)
            finally:
                docker_ops.stop_rm(state.container_name)
        else:
            http_detail = "skipped"
        objectives.append(
            ObjectiveResult(
                id="http-ok",
                description="HTTP 200 on published port",
                passed=http_ok,
                detail=http_detail,
            )
        )
        return CheckResult(
            passed=all(o.passed for o in objectives), objectives=objectives
        )
