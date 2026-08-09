"""Kubernetes troubleshooting scenarios."""

from __future__ import annotations

import json
import time
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from praxis.models import Assignment, CheckResult, ObjectiveResult
from praxis.modules.kubernetes import k8s_ops

NGINX = "nginx:1.25-alpine"


class K8sState(BaseModel):
    model_config = ConfigDict(frozen=True)

    namespace: str
    deployment: str = "web"
    service: str = "web"


def _wait_available(namespace: str, name: str, timeout: float = 90.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if k8s_ops.deployment_available(namespace, name):
            return True
        time.sleep(2)
    return False


class DeployUnavailableScenario:
    id = "deploy-unavailable"
    module = "kubernetes"
    title = "Make an unavailable Deployment ready"
    description = (
        "A Deployment is stuck unavailable due to a bad replica/image config. Fix it."
    )
    difficulty = "beginner"
    concepts = ["deployment", "replicas", "rollout"]
    state_model = K8sState

    def assignment(self) -> Assignment:
        return Assignment(
            title=self.title,
            summary=(
                "Namespace resources include Deployment `web` that never becomes "
                "Available (replicas set to 0). Fix manifests/live objects so "
                "`web` has at least one available replica."
            ),
            objectives=["Deployment web is Available with >=1 replica."],
        )

    def setup(self, repo_path: Path) -> K8sState:
        k8s_ops.require_k8s_tools()
        ns = k8s_ops.namespace_for(repo_path)
        k8s_ops.reset_namespace(ns)
        manifest = repo_path / "manifests" / "web.yaml"
        k8s_ops.write_text(
            manifest,
            f"""apiVersion: apps/v1
kind: Deployment
metadata:
  name: web
spec:
  replicas: 0
  selector:
    matchLabels:
      app: web
  template:
    metadata:
      labels:
        app: web
    spec:
      containers:
      - name: web
        image: {NGINX}
        ports:
        - containerPort: 80
""",
        )
        k8s_ops.apply_manifest(ns, manifest)
        return K8sState(namespace=ns)

    def validate(self, repo_path: Path, state: K8sState) -> CheckResult:
        # Re-apply learner manifests if present
        manifest = repo_path / "manifests" / "web.yaml"
        if manifest.is_file():
            k8s_ops.apply_manifest(state.namespace, manifest)
        ok = _wait_available(state.namespace, state.deployment, timeout=60)
        return CheckResult(
            passed=ok,
            objectives=[
                ObjectiveResult(
                    id="deploy-available",
                    description="Deployment web is Available",
                    passed=ok,
                    detail=None if ok else "not available",
                )
            ],
        )


class WrongImageScenario:
    id = "wrong-image"
    module = "kubernetes"
    title = "Fix a wrong container image"
    description = "Pods fail because the image tag does not exist. Correct the image."
    difficulty = "beginner"
    concepts = ["image", "ImagePullBackOff"]
    state_model = K8sState

    def assignment(self) -> Assignment:
        return Assignment(
            title=self.title,
            summary=(
                "Deployment `web` references a non-existent image. Change it to a "
                f"working image such as `{NGINX}` so the Deployment becomes Available."
            ),
            objectives=["Deployment web is Available."],
        )

    def setup(self, repo_path: Path) -> K8sState:
        k8s_ops.require_k8s_tools()
        ns = k8s_ops.namespace_for(repo_path)
        k8s_ops.reset_namespace(ns)
        manifest = repo_path / "manifests" / "web.yaml"
        k8s_ops.write_text(
            manifest,
            """apiVersion: apps/v1
kind: Deployment
metadata:
  name: web
spec:
  replicas: 1
  selector:
    matchLabels:
      app: web
  template:
    metadata:
      labels:
        app: web
    spec:
      containers:
      - name: web
        image: praxis.invalid/does-not-exist:latest
        ports:
        - containerPort: 80
""",
        )
        k8s_ops.apply_manifest(ns, manifest)
        return K8sState(namespace=ns)

    def validate(self, repo_path: Path, state: K8sState) -> CheckResult:
        manifest = repo_path / "manifests" / "web.yaml"
        if manifest.is_file():
            k8s_ops.apply_manifest(state.namespace, manifest)
        ok = _wait_available(state.namespace, "web", timeout=90)
        return CheckResult(
            passed=ok,
            objectives=[
                ObjectiveResult(
                    id="deploy-available",
                    description="Deployment web is Available",
                    passed=ok,
                    detail=None if ok else "still unavailable",
                )
            ],
        )


class SelectorMismatchScenario:
    id = "selector-mismatch"
    module = "kubernetes"
    title = "Fix a Service selector mismatch"
    description = (
        "A Service selects labels that do not match the Pods. Repair the selector."
    )
    difficulty = "beginner"
    concepts = ["service", "selector", "endpoints"]
    state_model = K8sState

    def assignment(self) -> Assignment:
        return Assignment(
            title=self.title,
            summary=(
                "Deployment `web` is healthy but Service `web` selects the wrong "
                "labels, so Endpoints stay empty. Fix the Service selector so "
                "Endpoints include Pod IPs."
            ),
            objectives=[
                "Deployment web is Available.",
                "Service web has ready endpoints.",
            ],
        )

    def setup(self, repo_path: Path) -> K8sState:
        k8s_ops.require_k8s_tools()
        ns = k8s_ops.namespace_for(repo_path)
        k8s_ops.reset_namespace(ns)
        deploy = repo_path / "manifests" / "web.yaml"
        k8s_ops.write_text(
            deploy,
            f"""apiVersion: apps/v1
kind: Deployment
metadata:
  name: web
spec:
  replicas: 1
  selector:
    matchLabels:
      app: web
  template:
    metadata:
      labels:
        app: web
    spec:
      containers:
      - name: web
        image: {NGINX}
        ports:
        - containerPort: 80
---
apiVersion: v1
kind: Service
metadata:
  name: web
spec:
  selector:
    app: website
  ports:
  - port: 80
    targetPort: 80
""",
        )
        k8s_ops.apply_manifest(ns, deploy)
        _wait_available(ns, "web", timeout=90)
        return K8sState(namespace=ns)

    def validate(self, repo_path: Path, state: K8sState) -> CheckResult:
        manifest = repo_path / "manifests" / "web.yaml"
        if manifest.is_file():
            k8s_ops.apply_manifest(state.namespace, manifest)
        dep_ok = _wait_available(state.namespace, "web", timeout=60)
        # give endpoints a moment
        ep_ok = False
        for _ in range(20):
            if k8s_ops.endpoints_ready(state.namespace, "web"):
                ep_ok = True
                break
            time.sleep(1)
        return CheckResult(
            passed=dep_ok and ep_ok,
            objectives=[
                ObjectiveResult(
                    id="deploy-available",
                    description="Deployment available",
                    passed=dep_ok,
                    detail=None if dep_ok else "deployment not ready",
                ),
                ObjectiveResult(
                    id="endpoints",
                    description="Service has endpoints",
                    passed=ep_ok,
                    detail=None if ep_ok else "no endpoints",
                ),
            ],
        )


class PortMismatchScenario:
    id = "port-mismatch"
    module = "kubernetes"
    title = "Fix mismatched Service and container ports"
    description = "Service targetPort does not match the container port. Align them."
    difficulty = "beginner"
    concepts = ["ports", "service"]
    state_model = K8sState

    def assignment(self) -> Assignment:
        return Assignment(
            title=self.title,
            summary=(
                "Service `web` targets the wrong port. Fix targetPort/containerPort "
                "so Endpoints work with the nginx container on port 80."
            ),
            objectives=["Service web has ready endpoints."],
        )

    def setup(self, repo_path: Path) -> K8sState:
        k8s_ops.require_k8s_tools()
        ns = k8s_ops.namespace_for(repo_path)
        k8s_ops.reset_namespace(ns)
        manifest = repo_path / "manifests" / "web.yaml"
        k8s_ops.write_text(
            manifest,
            f"""apiVersion: apps/v1
kind: Deployment
metadata:
  name: web
spec:
  replicas: 1
  selector:
    matchLabels:
      app: web
  template:
    metadata:
      labels:
        app: web
    spec:
      containers:
      - name: web
        image: {NGINX}
        ports:
        - containerPort: 80
---
apiVersion: v1
kind: Service
metadata:
  name: web
spec:
  selector:
    app: web
  ports:
  - port: 80
    targetPort: 8080
""",
        )
        k8s_ops.apply_manifest(ns, manifest)
        _wait_available(ns, "web", timeout=90)
        return K8sState(namespace=ns)

    def validate(self, repo_path: Path, state: K8sState) -> CheckResult:
        manifest = repo_path / "manifests" / "web.yaml"
        if manifest.is_file():
            k8s_ops.apply_manifest(state.namespace, manifest)
        ep_ok = False
        for _ in range(30):
            if k8s_ops.endpoints_ready(state.namespace, "web"):
                # endpoints exist even with wrong targetPort; check service targetPort
                break
            time.sleep(1)
        raw = k8s_ops.get_json(state.namespace, "service", "web")
        target_ok = False
        if raw:
            data = json.loads(raw)
            ports = data.get("spec", {}).get("ports", [])
            target_ok = any(p.get("targetPort") == 80 for p in ports)
        dep_ok = k8s_ops.deployment_available(state.namespace, "web")
        return CheckResult(
            passed=dep_ok and target_ok,
            objectives=[
                ObjectiveResult(
                    id="target-port",
                    description="Service targetPort is 80",
                    passed=target_ok,
                    detail=None if target_ok else "targetPort not 80",
                ),
                ObjectiveResult(
                    id="deploy-available",
                    description="Deployment available",
                    passed=dep_ok,
                    detail=None if dep_ok else "unavailable",
                ),
            ],
        )


class MissingConfigMapScenario:
    id = "missing-configmap"
    module = "kubernetes"
    title = "Provide a missing ConfigMap"
    description = "Pods mount a ConfigMap that does not exist. Create or fix it."
    difficulty = "intermediate"
    concepts = ["configmap", "volumes"]
    state_model = K8sState

    def assignment(self) -> Assignment:
        return Assignment(
            title=self.title,
            summary=(
                "Deployment `web` mounts ConfigMap `app-config` which is missing. "
                "Create it (key `message=hello`) so the Pods become Ready."
            ),
            objectives=["Deployment web is Available."],
        )

    def setup(self, repo_path: Path) -> K8sState:
        k8s_ops.require_k8s_tools()
        ns = k8s_ops.namespace_for(repo_path)
        k8s_ops.reset_namespace(ns)
        manifest = repo_path / "manifests" / "web.yaml"
        k8s_ops.write_text(
            manifest,
            f"""apiVersion: apps/v1
kind: Deployment
metadata:
  name: web
spec:
  replicas: 1
  selector:
    matchLabels:
      app: web
  template:
    metadata:
      labels:
        app: web
    spec:
      containers:
      - name: web
        image: {NGINX}
        volumeMounts:
        - name: cfg
          mountPath: /etc/config
      volumes:
      - name: cfg
        configMap:
          name: app-config
""",
        )
        k8s_ops.apply_manifest(ns, manifest)
        return K8sState(namespace=ns)

    def validate(self, repo_path: Path, state: K8sState) -> CheckResult:
        # Apply any manifests in folder
        manifests = repo_path / "manifests"
        if manifests.is_dir():
            for path in sorted(manifests.glob("*.yaml")):
                k8s_ops.apply_manifest(state.namespace, path)
        ok = _wait_available(state.namespace, "web", timeout=90)
        return CheckResult(
            passed=ok,
            objectives=[
                ObjectiveResult(
                    id="deploy-available",
                    description="Deployment available after ConfigMap fix",
                    passed=ok,
                    detail=None if ok else "still unavailable",
                )
            ],
        )


class MissingSecretScenario:
    id = "missing-secret"
    module = "kubernetes"
    title = "Provide a missing Secret"
    description = "Pods reference a Secret that does not exist. Create it."
    difficulty = "intermediate"
    concepts = ["secret"]
    state_model = K8sState

    def assignment(self) -> Assignment:
        return Assignment(
            title=self.title,
            summary=(
                "Deployment `web` expects Secret `app-secret` with key `token`. "
                "Create it so Pods become Ready."
            ),
            objectives=["Deployment web is Available."],
        )

    def setup(self, repo_path: Path) -> K8sState:
        k8s_ops.require_k8s_tools()
        ns = k8s_ops.namespace_for(repo_path)
        k8s_ops.reset_namespace(ns)
        manifest = repo_path / "manifests" / "web.yaml"
        k8s_ops.write_text(
            manifest,
            f"""apiVersion: apps/v1
kind: Deployment
metadata:
  name: web
spec:
  replicas: 1
  selector:
    matchLabels:
      app: web
  template:
    metadata:
      labels:
        app: web
    spec:
      containers:
      - name: web
        image: {NGINX}
        env:
        - name: TOKEN
          valueFrom:
            secretKeyRef:
              name: app-secret
              key: token
""",
        )
        k8s_ops.apply_manifest(ns, manifest)
        return K8sState(namespace=ns)

    def validate(self, repo_path: Path, state: K8sState) -> CheckResult:
        manifests = repo_path / "manifests"
        if manifests.is_dir():
            for path in sorted(manifests.glob("*.yaml")):
                k8s_ops.apply_manifest(state.namespace, path)
        ok = _wait_available(state.namespace, "web", timeout=90)
        return CheckResult(
            passed=ok,
            objectives=[
                ObjectiveResult(
                    id="deploy-available",
                    description="Deployment available after Secret fix",
                    passed=ok,
                    detail=None if ok else "still unavailable",
                )
            ],
        )


class BadProbeScenario:
    id = "bad-probe"
    module = "kubernetes"
    title = "Fix a broken readiness probe"
    description = "Readiness probe points at the wrong path/port. Repair it."
    difficulty = "intermediate"
    concepts = ["probes", "readiness"]
    state_model = K8sState

    def assignment(self) -> Assignment:
        return Assignment(
            title=self.title,
            summary=(
                "Deployment `web` never becomes Ready because the readiness probe "
                "checks the wrong port. Fix the probe for nginx on port 80."
            ),
            objectives=["Deployment web is Available."],
        )

    def setup(self, repo_path: Path) -> K8sState:
        k8s_ops.require_k8s_tools()
        ns = k8s_ops.namespace_for(repo_path)
        k8s_ops.reset_namespace(ns)
        manifest = repo_path / "manifests" / "web.yaml"
        k8s_ops.write_text(
            manifest,
            f"""apiVersion: apps/v1
kind: Deployment
metadata:
  name: web
spec:
  replicas: 1
  selector:
    matchLabels:
      app: web
  template:
    metadata:
      labels:
        app: web
    spec:
      containers:
      - name: web
        image: {NGINX}
        ports:
        - containerPort: 80
        readinessProbe:
          httpGet:
            path: /
            port: 8080
          initialDelaySeconds: 1
          periodSeconds: 2
""",
        )
        k8s_ops.apply_manifest(ns, manifest)
        return K8sState(namespace=ns)

    def validate(self, repo_path: Path, state: K8sState) -> CheckResult:
        manifest = repo_path / "manifests" / "web.yaml"
        if manifest.is_file():
            k8s_ops.apply_manifest(state.namespace, manifest)
        ok = _wait_available(state.namespace, "web", timeout=90)
        return CheckResult(
            passed=ok,
            objectives=[
                ObjectiveResult(
                    id="deploy-available",
                    description="Deployment available after probe fix",
                    passed=ok,
                    detail=None if ok else "still unavailable",
                )
            ],
        )


class WrongNamespaceScenario:
    id = "wrong-namespace"
    module = "kubernetes"
    title = "Apply resources to the correct namespace"
    description = (
        "Manifests were applied to the wrong namespace. Put `web` in the session namespace."
    )
    difficulty = "intermediate"
    concepts = ["namespace"]
    state_model = K8sState

    def assignment(self) -> Assignment:
        return Assignment(
            title=self.title,
            summary=(
                "Your session namespace should contain Deployment `web`, but it was "
                "applied elsewhere or missing. Ensure `web` exists and is Available "
                "in the session namespace shown in the workspace."
            ),
            objectives=["Deployment web is Available in the session namespace."],
        )

    def setup(self, repo_path: Path) -> K8sState:
        k8s_ops.require_k8s_tools()
        ns = k8s_ops.namespace_for(repo_path)
        k8s_ops.reset_namespace(ns)
        # Apply to default instead of session ns to create the mistake
        other = repo_path / "manifests" / "web.yaml"
        k8s_ops.write_text(
            other,
            f"""apiVersion: apps/v1
kind: Deployment
metadata:
  name: web
  namespace: default
spec:
  replicas: 1
  selector:
    matchLabels:
      app: web
  template:
    metadata:
      labels:
        app: web
    spec:
      containers:
      - name: web
        image: {NGINX}
        ports:
        - containerPort: 80
""",
        )
        k8s_ops.apply_manifest("default", other)
        # Hint file
        (repo_path / "NAMESPACE.txt").write_text(ns + "\n", encoding="utf-8")
        return K8sState(namespace=ns)

    def validate(self, repo_path: Path, state: K8sState) -> CheckResult:
        manifests = repo_path / "manifests"
        if manifests.is_dir():
            for path in sorted(manifests.glob("*.yaml")):
                # Prefer applying into session namespace explicitly
                text = path.read_text(encoding="utf-8")
                if f"namespace: {state.namespace}" in text or "namespace:" not in text:
                    k8s_ops.apply_manifest(state.namespace, path)
                else:
                    k8s_ops.apply_manifest(state.namespace, path)
        ok = _wait_available(state.namespace, "web", timeout=90)
        return CheckResult(
            passed=ok,
            objectives=[
                ObjectiveResult(
                    id="deploy-in-ns",
                    description="web Available in session namespace",
                    passed=ok,
                    detail=None if ok else f"missing in {state.namespace}",
                )
            ],
        )


class RolloutStuckScenario:
    id = "rollout-stuck"
    module = "kubernetes"
    title = "Unstick a failed rollout"
    description = (
        "A rolling update references a bad image and is stuck. Repair and complete the rollout."
    )
    difficulty = "intermediate"
    concepts = ["rollout", "image"]
    state_model = K8sState

    def assignment(self) -> Assignment:
        return Assignment(
            title=self.title,
            summary=(
                "Deployment `web` has a stuck rollout due to a bad image update. "
                "Restore a working image and make the Deployment Available again."
            ),
            objectives=["Deployment web is Available."],
        )

    def setup(self, repo_path: Path) -> K8sState:
        k8s_ops.require_k8s_tools()
        ns = k8s_ops.namespace_for(repo_path)
        k8s_ops.reset_namespace(ns)
        manifest = repo_path / "manifests" / "web.yaml"
        k8s_ops.write_text(
            manifest,
            f"""apiVersion: apps/v1
kind: Deployment
metadata:
  name: web
spec:
  replicas: 1
  selector:
    matchLabels:
      app: web
  template:
    metadata:
      labels:
        app: web
    spec:
      containers:
      - name: web
        image: {NGINX}
        ports:
        - containerPort: 80
""",
        )
        k8s_ops.apply_manifest(ns, manifest)
        _wait_available(ns, "web", timeout=90)
        # Break rollout
        bad = manifest.read_text(encoding="utf-8").replace(
            NGINX, "praxis.invalid/bad:latest"
        )
        manifest.write_text(bad, encoding="utf-8")
        k8s_ops.apply_manifest(ns, manifest)
        return K8sState(namespace=ns)

    def validate(self, repo_path: Path, state: K8sState) -> CheckResult:
        manifest = repo_path / "manifests" / "web.yaml"
        if manifest.is_file():
            k8s_ops.apply_manifest(state.namespace, manifest)
        ok = _wait_available(state.namespace, "web", timeout=120)
        return CheckResult(
            passed=ok,
            objectives=[
                ObjectiveResult(
                    id="deploy-available",
                    description="Rollout recovered; Deployment available",
                    passed=ok,
                    detail=None if ok else "still stuck",
                )
            ],
        )


class CrashloopDiagnoseScenario:
    id = "crashloop-diagnose"
    module = "kubernetes"
    title = "Diagnose a CrashLoopBackOff workload"
    description = (
        "A container command is wrong and pods crash. Fix the command so the Deployment is Available."
    )
    difficulty = "advanced"
    concepts = ["CrashLoopBackOff", "logs", "command"]
    state_model = K8sState

    def assignment(self) -> Assignment:
        return Assignment(
            title=self.title,
            summary=(
                "Pods for Deployment `web` are crash-looping because the container "
                "command is invalid. Fix the Pod template so nginx stays up and the "
                "Deployment becomes Available."
            ),
            objectives=["Deployment web is Available."],
        )

    def setup(self, repo_path: Path) -> K8sState:
        k8s_ops.require_k8s_tools()
        ns = k8s_ops.namespace_for(repo_path)
        k8s_ops.reset_namespace(ns)
        manifest = repo_path / "manifests" / "web.yaml"
        k8s_ops.write_text(
            manifest,
            f"""apiVersion: apps/v1
kind: Deployment
metadata:
  name: web
spec:
  replicas: 1
  selector:
    matchLabels:
      app: web
  template:
    metadata:
      labels:
        app: web
    spec:
      containers:
      - name: web
        image: {NGINX}
        command: ["sh", "-c", "exit 1"]
        ports:
        - containerPort: 80
""",
        )
        k8s_ops.apply_manifest(ns, manifest)
        return K8sState(namespace=ns)

    def validate(self, repo_path: Path, state: K8sState) -> CheckResult:
        manifest = repo_path / "manifests" / "web.yaml"
        if manifest.is_file():
            k8s_ops.apply_manifest(state.namespace, manifest)
        ok = _wait_available(state.namespace, "web", timeout=90)
        return CheckResult(
            passed=ok,
            objectives=[
                ObjectiveResult(
                    id="deploy-available",
                    description="CrashLoop fixed; Deployment available",
                    passed=ok,
                    detail=None if ok else "still crashing",
                )
            ],
        )


# Back-compat import names used by registry
DeployUnavailableScenario = DeployUnavailableScenario
WrongImageScenario = WrongImageScenario
SelectorMismatchScenario = SelectorMismatchScenario
