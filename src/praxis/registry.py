"""Explicit registry of training modules and scenarios."""

from __future__ import annotations

from pydantic import BaseModel

from praxis.errors import UnknownModuleError, UnknownScenarioError
from praxis.modules.base import Scenario

_REGISTRY: dict[str, dict[str, Scenario[BaseModel]]] = {}


def register(scenario: Scenario[BaseModel]) -> None:
    """Register a scenario implementation under ``(module, id)``."""
    module_scenarios = _REGISTRY.setdefault(scenario.module, {})
    if scenario.id in module_scenarios:
        raise ValueError(
            f"Scenario already registered: {scenario.module}/{scenario.id}"
        )
    module_scenarios[scenario.id] = scenario


def get_scenario(module_id: str, scenario_id: str) -> Scenario[BaseModel]:
    """Look up a scenario or raise a typed Praxis error."""
    module_scenarios = _REGISTRY.get(module_id)
    if module_scenarios is None:
        known = ", ".join(sorted(_REGISTRY)) or "(none)"
        raise UnknownModuleError(
            f"Unknown module {module_id!r}. Known modules: {known}."
        )
    scenario = module_scenarios.get(scenario_id)
    if scenario is None:
        known = ", ".join(sorted(module_scenarios)) or "(none)"
        raise UnknownScenarioError(
            f"Unknown scenario {scenario_id!r} for module {module_id!r}. "
            f"Known scenarios: {known}."
        )
    return scenario


def list_modules() -> list[str]:
    return sorted(_REGISTRY)


def list_scenarios(module_id: str) -> list[str]:
    module_scenarios = _REGISTRY.get(module_id)
    if module_scenarios is None:
        raise UnknownModuleError(f"Unknown module {module_id!r}.")
    return sorted(module_scenarios)


def clear_registry() -> None:
    """Remove all registrations (intended for tests)."""
    _REGISTRY.clear()
