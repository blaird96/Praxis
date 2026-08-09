"""Docker dockerfile-basic scenario."""

from __future__ import annotations

import time
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from praxis.errors import ScenarioSetupError
from praxis.models import Assignment, CheckResult, ObjectiveResult
from praxis.modules.docker import docker_ops
from praxis.modules.docker.lab_app import resource_prefix, write_app

DOCKERFILE = """\
FROM python:3.12-slim
WORKDIR /app
COPY app.py .
ENV PORT=8080
EXPOSE 8080
CMD ["python", "app.py"]
"""


class DockerfileBasicState(BaseModel):
    model_config = ConfigDict(frozen=True)

    image_tag: str
    container_name: str
    host_port: int
    prefix: str


class DockerfileBasicScenario:
    id: str = "dockerfile-basic"
    module: str = "docker"
    title: str = "Write a basic Dockerfile"
    description: str = (
        "Author a Dockerfile that builds and runs the provided HTTP app on port 8080."
    )
    difficulty: str | None = "beginner"
    concepts: list[str] = ["dockerfile", "build", "run", "ports"]
    state_model: type[DockerfileBasicState] = DockerfileBasicState

    def assignment(self) -> Assignment:
        return Assignment(
            title=self.title,
            summary=(
                "This workspace contains a tiny Python HTTP app (`app.py`). "
                "Write a `Dockerfile` that builds an image and can run the app "
                "listening on port 8080. Praxis will build tag "
                "`<prefix>-app:lab`, run a container publishing the assigned "
                "host port, and check that HTTP returns OK."
            ),
            objectives=[
                "Provide a working Dockerfile at the repo root.",
                "Image builds successfully.",
                "Container serves HTTP 200 on the published port.",
            ],
        )

    def setup(self, repo_path: Path) -> DockerfileBasicState:
        docker_ops.require_docker()
        prefix = resource_prefix(repo_path)
        docker_ops.cleanup_prefix(prefix)
        write_app(repo_path)
        host_port = 18000 + (abs(hash(prefix)) % 900)
        state = DockerfileBasicState(
            image_tag=f"{prefix}-app:lab",
            container_name=f"{prefix}-app",
            host_port=host_port,
            prefix=prefix,
        )
        if (repo_path / "Dockerfile").exists():
            (repo_path / "Dockerfile").unlink()
        self._verify_setup(repo_path, state)
        return state

    def _verify_setup(self, repo_path: Path, state: DockerfileBasicState) -> None:
        if not (repo_path / "app.py").is_file():
            raise ScenarioSetupError("app.py missing after setup")
        if (repo_path / "Dockerfile").exists():
            raise ScenarioSetupError("Dockerfile must not exist at start")

    def validate(
        self, repo_path: Path, state: DockerfileBasicState
    ) -> CheckResult:
        objectives: list[ObjectiveResult] = []
        dockerfile = repo_path / "Dockerfile"
        has_df = dockerfile.is_file()
        objectives.append(
            ObjectiveResult(
                id="dockerfile-present",
                description="Dockerfile exists",
                passed=has_df,
                detail=None if has_df else "Dockerfile missing",
            )
        )
        if not has_df:
            objectives.extend(
                [
                    ObjectiveResult(
                        id="image-builds",
                        description="Image builds",
                        passed=False,
                        detail="skipped",
                    ),
                    ObjectiveResult(
                        id="http-ok",
                        description="HTTP 200 on published port",
                        passed=False,
                        detail="skipped",
                    ),
                ]
            )
            return CheckResult(passed=False, objectives=objectives)

        docker_ops.cleanup_prefix(state.prefix)
        build_ok = True
        detail = None
        try:
            docker_ops.build(state.image_tag, repo_path)
        except Exception as exc:  # noqa: BLE001
            build_ok = False
            detail = str(exc)
        objectives.append(
            ObjectiveResult(
                id="image-builds",
                description="Image builds",
                passed=build_ok,
                detail=detail,
            )
        )
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
                    http_detail = "service did not respond with HTTP 200"
            except Exception as exc:  # noqa: BLE001
                http_detail = str(exc)
            finally:
                docker_ops.stop_rm(state.container_name)
        else:
            http_detail = "skipped; build failed"
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


# Reference Dockerfile kept for tests.
REFERENCE_DOCKERFILE = DOCKERFILE
