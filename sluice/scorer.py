from __future__ import annotations

from typing import Optional

import numpy as np

from sluice.models import (
    ProviderOption,
    RoutingExecutionReport,
    RoutingTask,
    privacy_rank,
    privacy_satisfies,
)
from sluice.benchmarks.model_benchmarks import get_model_benchmark

QUALITY_WEIGHT = 0.50
COST_WEIGHT = 0.25
LATENCY_WEIGHT = 0.15
RELIABILITY_WEIGHT = 0.10


def provider_map(task: RoutingTask) -> dict[str, ProviderOption]:
    return {provider.provider_id: provider for provider in task.candidate_providers}


def meets_task_requirements(task: RoutingTask, provider: ProviderOption) -> bool:
    capabilities = set(provider.capabilities)
    if not set(task.required_capabilities).issubset(capabilities):
        return False
    if provider.estimated_latency_ms > task.max_latency_ms:
        return False
    if provider.quality_score < task.min_quality_score:
        return False
    if task.max_cost_usd is not None and provider.estimated_cost_usd > task.max_cost_usd:
        return False
    if not privacy_satisfies(task.privacy_requirement, provider.privacy_tier):
        return False
    return True


def feasible_providers(task: RoutingTask) -> list[ProviderOption]:
    return [
        provider
        for provider in task.candidate_providers
        if meets_task_requirements(task, provider)
    ]


def reference_provider(task: RoutingTask) -> Optional[ProviderOption]:
    feasible = feasible_providers(task)
    if not feasible:
        return None
    return sorted(
        feasible,
        key=lambda provider: (
            provider.estimated_cost_usd,
            provider.estimated_latency_ms,
            -provider.reliability_score,
        ),
    )[0]


def _normalized_inverse(value: float, best: float, worst: float) -> float:
    if worst <= best:
        return 1.0
    clamped = max(best, min(worst, value))
    return 1.0 - ((clamped - best) / (worst - best))


def _closeness(expected: float, actual: float, floor: float = 1e-6) -> float:
    scale = max(abs(actual), floor)
    delta = abs(expected - actual) / scale
    return max(0.0, 1.0 - min(1.0, delta))


def _fallback_score(task: RoutingTask, report: RoutingExecutionReport) -> float:
    if not report.fallback_provider_ids:
        return 0.0

    providers = provider_map(task)
    seen: set[str] = set()
    usable = 0
    for provider_id in report.fallback_provider_ids:
        if provider_id == report.selected_provider_id or provider_id in seen:
            continue
        seen.add(provider_id)
        provider = providers.get(provider_id)
        if provider and meets_task_requirements(task, provider):
            usable += 1

    return min(1.0, usable / 2.0)


def score_one(
    report: Optional[RoutingExecutionReport],
    task: RoutingTask,
) -> float:
    if report is None:
        return 0.0

    providers = provider_map(task)
    selected = providers.get(report.selected_provider_id)
    if selected is None:
        return 0.0

    feasible = feasible_providers(task)
    if not feasible or not meets_task_requirements(task, selected):
        return 0.0

    reference = reference_provider(task)
    if reference is None:
        return 0.0
    # Compute dynamic model benchmark quality score based on workload type
    quality_score = get_model_benchmark(
        model_id=selected.model_id,
        workload_type=task.workload_type,
        required_capabilities=task.required_capabilities,
        fallback_score=selected.quality_score,
    )

    cost_score = min(1.0, reference.estimated_cost_usd / max(selected.estimated_cost_usd, 1e-6))
    latency_values = [provider.estimated_latency_ms for provider in feasible]
    latency_score = _normalized_inverse(
        float(selected.estimated_latency_ms),
        float(min(latency_values)),
        float(max(latency_values)),
    )
    reliability_score = selected.reliability_score

    gate = 1.0

    total = gate * (
        (QUALITY_WEIGHT * quality_score)
        + (COST_WEIGHT * cost_score)
        + (LATENCY_WEIGHT * latency_score)
        + (RELIABILITY_WEIGHT * reliability_score)
    )
    return round(max(0.0, min(1.0, float(total))), 6)


def score_many(
    reports: list[Optional[RoutingExecutionReport]],
    task: RoutingTask,
) -> np.ndarray:
    return np.array([score_one(report, task) for report in reports], dtype=np.float32)
