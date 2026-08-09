"""Tests for explicit scenario registry lookup."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import BaseModel

from praxis.errors import UnknownModuleError, UnknownScenarioError
from praxis.models import Assignment, CheckResult, ObjectiveResult
from praxis.modules.base import Scenario
from praxis.registry import (
    bootstrap_registry,
    clear_registry,
    get_scenario,
    list_modules,
    list_scenarios,
    register,
)


class _DummyState(BaseModel):
    marker: str


class _DummyScenario:
    def __init__(self, module: str, scenario_id: str) -> None:
        self._module = module
        self._id = scenario_id

    @property
    def id(self) -> str:
        return self._id

    @property
    def module(self) -> str:
        return self._module

    @property
    def title(self) -> str:
        return "Dummy"

    @property
    def description(self) -> str:
        return "Dummy scenario for registry tests"

    @property
    def difficulty(self) -> str | None:
        return None

    @property
    def concepts(self) -> list[str]:
        return []

    @property
    def state_model(self) -> type[_DummyState]:
        return _DummyState
    def assignment(self) -> Assignment:
        return Assignment(title="Dummy", summary="test")

    def setup(self, repo_path: Path) -> _DummyState:
        return _DummyState(marker=str(repo_path))

    def validate(self, repo_path: Path, state: _DummyState) -> CheckResult:
        return CheckResult(
            passed=True,
            objectives=[
                ObjectiveResult(
                    id="ok",
                    description="always passes",
                    passed=True,
                )
            ],
        )


@pytest.fixture(autouse=True)
def _clean_registry() -> None:
    clear_registry()
    yield
    clear_registry()


def test_register_and_get_scenario() -> None:
    scenario = _DummyScenario("git", "merge-conflict")
    register(scenario)
    assert isinstance(scenario, Scenario)

    loaded = get_scenario("git", "merge-conflict")
    assert loaded is scenario
    assert list_modules() == ["git"]
    assert list_scenarios("git") == ["merge-conflict"]


def test_unknown_module() -> None:
    with pytest.raises(UnknownModuleError, match="Unknown module 'missing-mod'"):
        get_scenario("missing-mod", "basic")


def test_unknown_scenario() -> None:
    register(_DummyScenario("git", "merge-conflict"))
    with pytest.raises(UnknownScenarioError, match="Unknown scenario 'rebase'"):
        get_scenario("git", "rebase")


def test_duplicate_registration_rejected() -> None:
    register(_DummyScenario("git", "merge-conflict"))
    with pytest.raises(ValueError, match="already registered"):
        register(_DummyScenario("git", "merge-conflict"))


def test_list_scenarios_unknown_module() -> None:
    with pytest.raises(UnknownModuleError):
        list_scenarios("missing")


def test_bootstrap_registry_registers_builtins_idempotently() -> None:
    clear_registry()
    bootstrap_registry()
    first = get_scenario("git", "merge-conflict")
    bootstrap_registry()
    second = get_scenario("git", "merge-conflict")
    assert first is second
    assert "git" in list_modules()
    assert "docker" in list_modules()
    assert "kubernetes" in list_modules()
    assert "feature-branch" in list_scenarios("git")
    assert "dockerfile-basic" in list_scenarios("docker")
    assert "deploy-unavailable" in list_scenarios("kubernetes")
