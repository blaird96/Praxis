"""Additional Docker scenarios: build-context through compose."""

from __future__ import annotations

import re
import time
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from praxis.models import Assignment, CheckResult, ObjectiveResult
from praxis.modules.docker import docker_ops
from praxis.modules.docker.lab_app import resource_prefix, write_app


def _port(prefix: str, base: int) -> int:
    return base + (abs(hash(prefix)) % 700)


class BuildContextState(BaseModel):
    model_config = ConfigDict(frozen=True)

    image_tag: str
    prefix: str


class BuildContextScenario:
    id = "build-context"
    module = "docker"
    title = "Fix build context and dockerignore"
    description = (
        "Ensure the image includes app.py but excludes secrets.env via .dockerignore."
    )
    difficulty = "intermediate"
    concepts = ["build-context", "dockerignore", "COPY"]
    state_model = BuildContextState

    def assignment(self) -> Assignment:
        return Assignment(
            title=self.title,
            summary=(
                "Fix the Dockerfile/.dockerignore so the image contains `/app/app.py` "
                "but does **not** contain `/app/secrets.env`."
            ),
            objectives=[
                "Image builds.",
                "Image contains /app/app.py.",
                "Image does not contain /app/secrets.env.",
            ],
        )

    def setup(self, repo_path: Path) -> BuildContextState:
        docker_ops.require_docker()
        prefix = resource_prefix(repo_path)
        docker_ops.cleanup_prefix(prefix)
        write_app(repo_path)
        (repo_path / "secrets.env").write_text("TOKEN=super-secret\n", encoding="utf-8")
        (repo_path / "Dockerfile").write_text(
            "FROM python:3.12-slim\nWORKDIR /app\nCOPY . .\nCMD [\"python\", \"app.py\"]\n",
            encoding="utf-8",
        )
        # Broken: no dockerignore, secrets leak
        state = BuildContextState(image_tag=f"{prefix}-ctx:lab", prefix=prefix)
        return state

    def validate(self, repo_path: Path, state: BuildContextState) -> CheckResult:
        docker_ops.cleanup_prefix(state.prefix)
        build_ok = True
        detail = None
        try:
            docker_ops.build(state.image_tag, repo_path)
        except Exception as exc:  # noqa: BLE001
            build_ok = False
            detail = str(exc)
        has_app = False
        no_secret = False
        if build_ok:
            has_app = docker_ops.image_has_file(state.image_tag, "/app/app.py")
            no_secret = not docker_ops.image_has_file(
                state.image_tag, "/app/secrets.env"
            )
        return CheckResult(
            passed=build_ok and has_app and no_secret,
            objectives=[
                ObjectiveResult(
                    id="builds",
                    description="Image builds",
                    passed=build_ok,
                    detail=detail,
                ),
                ObjectiveResult(
                    id="has-app",
                    description="Image contains /app/app.py",
                    passed=has_app,
                    detail=None if has_app else "app.py missing in image",
                ),
                ObjectiveResult(
                    id="no-secret",
                    description="Image excludes secrets.env",
                    passed=no_secret,
                    detail=None if no_secret else "secrets.env still in image",
                ),
            ],
        )


class PortsAndEnvState(BaseModel):
    model_config = ConfigDict(frozen=True)

    image_tag: str
    container_name: str
    host_port: int
    prefix: str
    expected_port: str


class PortsAndEnvScenario:
    id = "ports-and-env"
    module = "docker"
    title = "Configure ports and environment variables"
    description = "Make the container listen using PORT=9090 and publish that port."
    difficulty = "beginner"
    concepts = ["ports", "environment-variables"]
    state_model = PortsAndEnvState

    def assignment(self) -> Assignment:
        return Assignment(
            title=self.title,
            summary=(
                "Update the Dockerfile so the app listens on PORT 9090 (ENV + EXPOSE). "
                "Praxis runs the image publishing the assigned host port to 9090."
            ),
            objectives=[
                "Image builds with ENV PORT=9090.",
                "HTTP 200 on the published host port.",
            ],
        )

    def setup(self, repo_path: Path) -> PortsAndEnvState:
        docker_ops.require_docker()
        prefix = resource_prefix(repo_path)
        docker_ops.cleanup_prefix(prefix)
        write_app(repo_path)
        (repo_path / "Dockerfile").write_text(
            "FROM python:3.12-slim\nWORKDIR /app\nCOPY app.py .\n"
            "ENV PORT=8080\nEXPOSE 8080\nCMD [\"python\", \"app.py\"]\n",
            encoding="utf-8",
        )
        return PortsAndEnvState(
            image_tag=f"{prefix}-env:lab",
            container_name=f"{prefix}-env",
            host_port=_port(prefix, 18200),
            prefix=prefix,
            expected_port="9090",
        )

    def validate(self, repo_path: Path, state: PortsAndEnvState) -> CheckResult:
        text = (repo_path / "Dockerfile").read_text(encoding="utf-8")
        env_ok = re.search(r"ENV\s+PORT=9090", text) is not None
        docker_ops.cleanup_prefix(state.prefix)
        build_ok = False
        http_ok = False
        detail = None
        try:
            docker_ops.build(state.image_tag, repo_path)
            build_ok = True
            docker_ops.run_detached(
                state.container_name,
                state.image_tag,
                publish=[f"{state.host_port}:9090"],
            )
            for _ in range(20):
                if docker_ops.http_ok(f"http://127.0.0.1:{state.host_port}/"):
                    http_ok = True
                    break
                time.sleep(0.25)
        except Exception as exc:  # noqa: BLE001
            detail = str(exc)
        finally:
            docker_ops.stop_rm(state.container_name)
        return CheckResult(
            passed=env_ok and build_ok and http_ok,
            objectives=[
                ObjectiveResult(
                    id="env-port",
                    description="Dockerfile sets ENV PORT=9090",
                    passed=env_ok,
                    detail=None if env_ok else "ENV PORT=9090 not found",
                ),
                ObjectiveResult(
                    id="builds",
                    description="Image builds",
                    passed=build_ok,
                    detail=detail,
                ),
                ObjectiveResult(
                    id="http-ok",
                    description="HTTP 200 via published 9090",
                    passed=http_ok,
                    detail=None if http_ok else "no response",
                ),
            ],
        )


class VolumeBindState(BaseModel):
    model_config = ConfigDict(frozen=True)

    image_tag: str
    container_name: str
    prefix: str


class VolumeBindScenario:
    id = "volume-bind"
    module = "docker"
    title = "Inject config with a bind mount"
    description = (
        "Run so /data/config.txt from the workspace bind mount is visible in the container."
    )
    difficulty = "intermediate"
    concepts = ["volumes", "bind-mount"]
    state_model = VolumeBindState

    def assignment(self) -> Assignment:
        return Assignment(
            title=self.title,
            summary=(
                "Create `data/config.txt` with content `mounted=1` and ensure a "
                "container run with a bind mount makes `/data/config.txt` readable. "
                "Provide a `run.sh` (or Dockerfile + docs) — Praxis validates by "
                "building `Dockerfile` and running with "
                "`-v <repo>/data:/data` then reading the file."
            ),
            objectives=[
                "data/config.txt exists with mounted=1.",
                "Image builds.",
                "Bind-mounted file is visible at /data/config.txt in the container.",
            ],
        )

    def setup(self, repo_path: Path) -> VolumeBindState:
        docker_ops.require_docker()
        prefix = resource_prefix(repo_path)
        docker_ops.cleanup_prefix(prefix)
        write_app(repo_path)
        (repo_path / "Dockerfile").write_text(
            "FROM python:3.12-slim\nWORKDIR /app\nCOPY app.py .\nCMD [\"sleep\", \"3600\"]\n",
            encoding="utf-8",
        )
        (repo_path / "data").mkdir(exist_ok=True)
        return VolumeBindState(
            image_tag=f"{prefix}-vol:lab",
            container_name=f"{prefix}-vol",
            prefix=prefix,
        )

    def validate(self, repo_path: Path, state: VolumeBindState) -> CheckResult:
        cfg = repo_path / "data" / "config.txt"
        cfg_ok = cfg.is_file() and "mounted=1" in cfg.read_text(encoding="utf-8")
        docker_ops.cleanup_prefix(state.prefix)
        visible = False
        build_ok = False
        detail = None
        try:
            docker_ops.build(state.image_tag, repo_path)
            build_ok = True
            mount = f"{repo_path / 'data'}:/data"
            docker_ops.run_detached(
                state.container_name, state.image_tag, volumes=[mount]
            )
            result = docker_ops.exec_run(
                state.container_name, "cat", "/data/config.txt"
            )
            visible = result.returncode == 0 and "mounted=1" in result.stdout
        except Exception as exc:  # noqa: BLE001
            detail = str(exc)
        finally:
            docker_ops.stop_rm(state.container_name)
        return CheckResult(
            passed=cfg_ok and build_ok and visible,
            objectives=[
                ObjectiveResult(
                    id="config-file",
                    description="data/config.txt contains mounted=1",
                    passed=cfg_ok,
                    detail=None if cfg_ok else "missing config",
                ),
                ObjectiveResult(
                    id="builds",
                    description="Image builds",
                    passed=build_ok,
                    detail=detail,
                ),
                ObjectiveResult(
                    id="mount-visible",
                    description="Bind mount visible in container",
                    passed=visible,
                    detail=None if visible else "cannot read /data/config.txt",
                ),
            ],
        )


class NonrootUserState(BaseModel):
    model_config = ConfigDict(frozen=True)

    image_tag: str
    container_name: str
    prefix: str


class NonrootUserScenario:
    id = "nonroot-user"
    module = "docker"
    title = "Run the container as a non-root user"
    description = "Configure the image so the main process runs as a non-root user."
    difficulty = "intermediate"
    concepts = ["USER", "non-root"]
    state_model = NonrootUserState

    def assignment(self) -> Assignment:
        return Assignment(
            title=self.title,
            summary=(
                "Update the Dockerfile so the container process runs as a non-root "
                "user (uid != 0)."
            ),
            objectives=[
                "Image builds.",
                "Container process user is non-root.",
            ],
        )

    def setup(self, repo_path: Path) -> NonrootUserState:
        docker_ops.require_docker()
        prefix = resource_prefix(repo_path)
        docker_ops.cleanup_prefix(prefix)
        write_app(repo_path)
        (repo_path / "Dockerfile").write_text(
            "FROM python:3.12-slim\nWORKDIR /app\nCOPY app.py .\n"
            "CMD [\"sleep\", \"3600\"]\n",
            encoding="utf-8",
        )
        return NonrootUserState(
            image_tag=f"{prefix}-user:lab",
            container_name=f"{prefix}-user",
            prefix=prefix,
        )

    def validate(self, repo_path: Path, state: NonrootUserState) -> CheckResult:
        docker_ops.cleanup_prefix(state.prefix)
        nonroot = False
        build_ok = False
        detail = None
        try:
            docker_ops.build(state.image_tag, repo_path)
            build_ok = True
            docker_ops.run_detached(state.container_name, state.image_tag)
            result = docker_ops.exec_run(state.container_name, "id", "-u")
            if result.returncode == 0:
                nonroot = result.stdout.strip() != "0"
        except Exception as exc:  # noqa: BLE001
            detail = str(exc)
        finally:
            docker_ops.stop_rm(state.container_name)
        return CheckResult(
            passed=build_ok and nonroot,
            objectives=[
                ObjectiveResult(
                    id="builds",
                    description="Image builds",
                    passed=build_ok,
                    detail=detail,
                ),
                ObjectiveResult(
                    id="nonroot",
                    description="Process runs as non-root",
                    passed=nonroot,
                    detail=None if nonroot else "uid is 0 or unknown",
                ),
            ],
        )


class LayerCacheState(BaseModel):
    model_config = ConfigDict(frozen=True)

    prefix: str


class LayerCacheScenario:
    id = "layer-cache"
    module = "docker"
    title = "Order Dockerfile layers for caching"
    description = (
        "Reorder the Dockerfile so dependency install happens before copying app code."
    )
    difficulty = "intermediate"
    concepts = ["layers", "cache"]
    state_model = LayerCacheState

    def assignment(self) -> Assignment:
        return Assignment(
            title=self.title,
            summary=(
                "Fix Dockerfile layer order: copy requirements and install deps "
                "**before** copying `app.py`."
            ),
            objectives=[
                "requirements.txt is copied before app.py in the Dockerfile.",
                "Image still builds.",
            ],
        )

    def setup(self, repo_path: Path) -> LayerCacheState:
        docker_ops.require_docker()
        prefix = resource_prefix(repo_path)
        write_app(repo_path)
        (repo_path / "requirements.txt").write_text("# no deps\n", encoding="utf-8")
        (repo_path / "Dockerfile").write_text(
            "FROM python:3.12-slim\nWORKDIR /app\n"
            "COPY app.py .\nCOPY requirements.txt .\n"
            "RUN pip install -r requirements.txt\n"
            "CMD [\"python\", \"app.py\"]\n",
            encoding="utf-8",
        )
        return LayerCacheState(prefix=prefix)

    def validate(self, repo_path: Path, state: LayerCacheState) -> CheckResult:
        text = (repo_path / "Dockerfile").read_text(encoding="utf-8")
        req_pos = text.find("COPY requirements.txt")
        app_pos = text.find("COPY app.py")
        order_ok = req_pos != -1 and app_pos != -1 and req_pos < app_pos
        build_ok = True
        detail = None
        try:
            docker_ops.build(f"{state.prefix}-cache:lab", repo_path)
        except Exception as exc:  # noqa: BLE001
            build_ok = False
            detail = str(exc)
        return CheckResult(
            passed=order_ok and build_ok,
            objectives=[
                ObjectiveResult(
                    id="layer-order",
                    description="requirements copied before app.py",
                    passed=order_ok,
                    detail=None if order_ok else "order incorrect",
                ),
                ObjectiveResult(
                    id="builds",
                    description="Image builds",
                    passed=build_ok,
                    detail=detail,
                ),
            ],
        )


class MultistageBuildState(BaseModel):
    model_config = ConfigDict(frozen=True)

    image_tag: str
    container_name: str
    host_port: int
    prefix: str


class MultistageBuildScenario:
    id = "multistage-build"
    module = "docker"
    title = "Use a multi-stage build"
    description = (
        "Produce a runtime image that runs the app but does not include gcc."
    )
    difficulty = "intermediate"
    concepts = ["multi-stage", "runtime-image"]
    state_model = MultistageBuildState

    def assignment(self) -> Assignment:
        return Assignment(
            title=self.title,
            summary=(
                "Rewrite the Dockerfile as multi-stage. Final image should run the "
                "HTTP app and must not contain `/usr/bin/gcc`."
            ),
            objectives=[
                "Dockerfile contains multiple FROM stages.",
                "Final image builds and serves HTTP.",
                "Final image lacks /usr/bin/gcc.",
            ],
        )

    def setup(self, repo_path: Path) -> MultistageBuildState:
        docker_ops.require_docker()
        prefix = resource_prefix(repo_path)
        docker_ops.cleanup_prefix(prefix)
        write_app(repo_path)
        (repo_path / "Dockerfile").write_text(
            "FROM python:3.12-slim\nRUN apt-get update && apt-get install -y gcc\n"
            "WORKDIR /app\nCOPY app.py .\nCMD [\"python\", \"app.py\"]\n",
            encoding="utf-8",
        )
        return MultistageBuildState(
            image_tag=f"{prefix}-ms:lab",
            container_name=f"{prefix}-ms",
            host_port=_port(prefix, 18300),
            prefix=prefix,
        )

    def validate(self, repo_path: Path, state: MultistageBuildState) -> CheckResult:
        text = (repo_path / "Dockerfile").read_text(encoding="utf-8")
        stages = len(re.findall(r"(?im)^FROM\s+", text))
        multi = stages >= 2
        docker_ops.cleanup_prefix(state.prefix)
        build_ok = False
        http_ok = False
        no_gcc = False
        detail = None
        try:
            docker_ops.build(state.image_tag, repo_path)
            build_ok = True
            no_gcc = not docker_ops.image_has_file(state.image_tag, "/usr/bin/gcc")
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
        except Exception as exc:  # noqa: BLE001
            detail = str(exc)
        finally:
            docker_ops.stop_rm(state.container_name)
        return CheckResult(
            passed=multi and build_ok and http_ok and no_gcc,
            objectives=[
                ObjectiveResult(
                    id="multi-stage",
                    description="Dockerfile has multiple FROM stages",
                    passed=multi,
                    detail=None if multi else f"FROM count={stages}",
                ),
                ObjectiveResult(
                    id="builds-runs",
                    description="Final image builds and serves HTTP",
                    passed=build_ok and http_ok,
                    detail=detail,
                ),
                ObjectiveResult(
                    id="no-gcc",
                    description="Final image lacks gcc",
                    passed=no_gcc,
                    detail=None if no_gcc else "gcc still present",
                ),
            ],
        )


class ComposeTwoServiceState(BaseModel):
    model_config = ConfigDict(frozen=True)

    prefix: str
    host_port: int


class ComposeTwoServiceScenario:
    id = "compose-two-service"
    module = "docker"
    title = "Run app and dependency with Compose"
    description = (
        "Provide a compose file with web + redis so the web service responds on the published port."
    )
    difficulty = "intermediate"
    concepts = ["compose", "networking"]
    state_model = ComposeTwoServiceState

    def assignment(self) -> Assignment:
        return Assignment(
            title=self.title,
            summary=(
                "Create `compose.yaml` with services `web` (this app) and `redis` "
                f"(image redis:7). Publish web on the host port recorded in setup "
                "state via Praxis validation (maps to container 8080). "
                "`docker compose up -d` must leave web healthy enough to return HTTP 200."
            ),
            objectives=[
                "compose.yaml defines web and redis services.",
                "compose up yields HTTP 200 on the published port.",
            ],
        )

    def setup(self, repo_path: Path) -> ComposeTwoServiceState:
        docker_ops.require_docker()
        prefix = resource_prefix(repo_path)
        write_app(repo_path)
        (repo_path / "Dockerfile").write_text(
            "FROM python:3.12-slim\nWORKDIR /app\nCOPY app.py .\n"
            "ENV PORT=8080\nCMD [\"python\", \"app.py\"]\n",
            encoding="utf-8",
        )
        return ComposeTwoServiceState(
            prefix=prefix, host_port=_port(prefix, 18400)
        )

    def validate(
        self, repo_path: Path, state: ComposeTwoServiceState
    ) -> CheckResult:
        compose = repo_path / "compose.yaml"
        if not compose.is_file():
            compose = repo_path / "docker-compose.yml"
        has_file = compose.is_file()
        text = compose.read_text(encoding="utf-8") if has_file else ""
        has_web = "web:" in text
        has_redis = "redis:" in text
        http_ok = False
        detail = None
        if has_file and has_web and has_redis:
            # Inject published port if learner used 8080:8080 — we still try compose up
            try:
                from praxis.process import run

                run(
                    [
                        "docker",
                        "compose",
                        "-p",
                        state.prefix,
                        "down",
                        "-v",
                    ],
                    cwd=repo_path,
                    allowed_returncodes={0, 1},
                )
                # Ensure publish matches state host port by writing override
                override = (
                    "services:\n  web:\n    ports:\n"
                    f'      - "{state.host_port}:8080"\n'
                )
                (repo_path / "compose.override.yaml").write_text(
                    override, encoding="utf-8"
                )
                run(
                    ["docker", "compose", "-p", state.prefix, "up", "-d", "--build"],
                    cwd=repo_path,
                )
                for _ in range(40):
                    if docker_ops.http_ok(f"http://127.0.0.1:{state.host_port}/"):
                        http_ok = True
                        break
                    time.sleep(0.5)
                if not http_ok:
                    detail = "web did not respond"
            except Exception as exc:  # noqa: BLE001
                detail = str(exc)
            finally:
                from praxis.process import run

                run(
                    ["docker", "compose", "-p", state.prefix, "down", "-v"],
                    cwd=repo_path,
                    allowed_returncodes={0, 1},
                )
        return CheckResult(
            passed=has_file and has_web and has_redis and http_ok,
            objectives=[
                ObjectiveResult(
                    id="compose-services",
                    description="compose defines web and redis",
                    passed=has_file and has_web and has_redis,
                    detail=None
                    if has_file and has_web and has_redis
                    else "compose file incomplete",
                ),
                ObjectiveResult(
                    id="http-ok",
                    description="compose stack serves HTTP 200",
                    passed=http_ok,
                    detail=detail,
                ),
            ],
        )


class StartupFailureState(BaseModel):
    model_config = ConfigDict(frozen=True)

    image_tag: str
    container_name: str
    prefix: str


class StartupFailureScenario:
    id = "startup-failure"
    module = "docker"
    title = "Diagnose a container startup failure"
    description = (
        "Fix the broken command/env so the container stays running and serves HTTP."
    )
    difficulty = "intermediate"
    concepts = ["logs", "startup", "CMD"]
    state_model = StartupFailureState

    def assignment(self) -> Assignment:
        return Assignment(
            title=self.title,
            summary=(
                "The Dockerfile CMD is wrong so the container exits immediately. "
                "Fix it so the app starts and responds to HTTP."
            ),
            objectives=[
                "Image builds.",
                "Container stays up and returns HTTP 200.",
            ],
        )

    def setup(self, repo_path: Path) -> StartupFailureState:
        docker_ops.require_docker()
        prefix = resource_prefix(repo_path)
        docker_ops.cleanup_prefix(prefix)
        write_app(repo_path)
        (repo_path / "Dockerfile").write_text(
            "FROM python:3.12-slim\nWORKDIR /app\nCOPY app.py .\n"
            "ENV PORT=8080\nCMD [\"python\", \"missing.py\"]\n",
            encoding="utf-8",
        )
        return StartupFailureState(
            image_tag=f"{prefix}-boot:lab",
            container_name=f"{prefix}-boot",
            prefix=prefix,
        )

    def validate(
        self, repo_path: Path, state: StartupFailureState
    ) -> CheckResult:
        host_port = _port(state.prefix, 18500)
        docker_ops.cleanup_prefix(state.prefix)
        build_ok = False
        http_ok = False
        detail = None
        try:
            docker_ops.build(state.image_tag, repo_path)
            build_ok = True
            docker_ops.run_detached(
                state.container_name,
                state.image_tag,
                publish=[f"{host_port}:8080"],
            )
            for _ in range(20):
                if docker_ops.http_ok(f"http://127.0.0.1:{host_port}/"):
                    http_ok = True
                    break
                time.sleep(0.25)
            if not http_ok:
                detail = "container not serving"
        except Exception as exc:  # noqa: BLE001
            detail = str(exc)
        finally:
            docker_ops.stop_rm(state.container_name)
        return CheckResult(
            passed=build_ok and http_ok,
            objectives=[
                ObjectiveResult(
                    id="builds",
                    description="Image builds",
                    passed=build_ok,
                    detail=detail if not build_ok else None,
                ),
                ObjectiveResult(
                    id="http-ok",
                    description="Container serves HTTP 200",
                    passed=http_ok,
                    detail=detail if not http_ok else None,
                ),
            ],
        )
