"""Catalog and health endpoints."""

from __future__ import annotations

from fastapi import APIRouter

from praxis.api.schemas import (
    CatalogResponse,
    HealthResponse,
    ModuleInfo,
    ScenarioInfo,
)
from praxis.modules.prerequisites import module_availability
from praxis.progress import load_progress, scenario_completed
from praxis.registry import (
    bootstrap_registry,
    get_scenario,
    list_modules,
    list_scenarios,
)

router = APIRouter(tags=["catalog"])


def _module_title(module_id: str) -> str:
    return module_id.replace("-", " ").replace("_", " ").title()


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse()


@router.get("/catalog", response_model=CatalogResponse)
def catalog() -> CatalogResponse:
    bootstrap_registry()
    progress = load_progress()
    modules: list[ModuleInfo] = []
    for module_id in list_modules():
        available, reason = module_availability(module_id)
        scenarios = []
        for scenario_id in list_scenarios(module_id):
            scenario = get_scenario(module_id, scenario_id)
            scenarios.append(
                ScenarioInfo(
                    id=scenario_id,
                    title=scenario.title,
                    description=scenario.description,
                    difficulty=scenario.difficulty,
                    concepts=list(getattr(scenario, "concepts", []) or []),
                    available=available,
                    unavailable_reason=reason,
                    completed=scenario_completed(module_id, scenario_id, progress),
                )
            )
        modules.append(
            ModuleInfo(
                id=module_id,
                title=_module_title(module_id),
                scenarios=scenarios,
                available=available,
                unavailable_reason=reason,
            )
        )
    return CatalogResponse(modules=modules)
