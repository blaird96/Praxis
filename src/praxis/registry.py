"""Explicit registry of training modules and scenarios."""

from __future__ import annotations

from typing import Any

from praxis.errors import UnknownModuleError, UnknownScenarioError
from praxis.modules.base import Scenario

_REGISTRY: dict[str, dict[str, Scenario[Any]]] = {}


def register(scenario: Scenario[Any]) -> None:
    """Register a scenario implementation under ``(module, id)``.

    Raises ``ValueError`` if the same ``(module, id)`` is already present.
    Prefer :func:`bootstrap_registry` for built-in scenarios at startup.
    """
    module_scenarios = _REGISTRY.setdefault(scenario.module, {})
    if scenario.id in module_scenarios:
        raise ValueError(
            f"Scenario already registered: {scenario.module}/{scenario.id}"
        )
    module_scenarios[scenario.id] = scenario


def _ensure_builtin(scenario: Scenario[Any]) -> None:
    """Register ``scenario`` only if that id is not already present."""
    module_scenarios = _REGISTRY.setdefault(scenario.module, {})
    if scenario.id not in module_scenarios:
        module_scenarios[scenario.id] = scenario


def bootstrap_registry() -> None:
    """Ensure built-in scenarios are registered.

    Idempotent: safe to call multiple times. Does not overwrite an existing
    registration for the same ``(module, id)``. Does not depend on import-time
    side effects — callers (CLI/runner) must invoke this at startup.
    """
    from praxis.modules.git.scenarios.merge_conflict import MergeConflictScenario

    _ensure_builtin(MergeConflictScenario())


def get_scenario(module_id: str, scenario_id: str) -> Scenario[Any]:
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


def list_registered_scenarios() -> list[tuple[str, str]]:
    """Return ``(module_id, scenario_id)`` pairs currently in the registry."""
    pairs: list[tuple[str, str]] = []
    for module_id in list_modules():
        for scenario_id in list_scenarios(module_id):
            pairs.append((module_id, scenario_id))
    return pairs


def clear_registry() -> None:
    """Remove all registrations (intended for tests)."""
    _REGISTRY.clear()
