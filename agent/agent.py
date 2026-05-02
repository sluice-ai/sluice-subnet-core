#!/usr/bin/env python3
from __future__ import annotations


PRIVACY_ORDER = {"public": 0, "internal": 1, "confidential": 2}


def _privacy_ok(required: str, actual: str) -> bool:
    return PRIVACY_ORDER.get(actual, -1) >= PRIVACY_ORDER.get(required, -1)


def _capabilities(provider: dict) -> set[str]:
    return {str(cap).strip().lower() for cap in provider.get("capabilities", [])}


def _is_feasible(task: dict, provider: dict) -> bool:
    required_caps = {str(cap).strip().lower() for cap in task.get("required_capabilities", [])}
    if not required_caps.issubset(_capabilities(provider)):
        return False
    if float(provider.get("estimated_latency_ms", 0)) > float(task.get("max_latency_ms", 0)):
        return False
    if float(provider.get("quality_score", 0.0)) < float(task.get("min_quality_score", 0.0)):
        return False
    max_cost = task.get("max_cost_usd")
    if max_cost is not None and float(provider.get("estimated_cost_usd", 0.0)) > float(max_cost):
        return False
    if not _privacy_ok(
        str(task.get("privacy_requirement", "public")),
        str(provider.get("privacy_tier", "public")),
    ):
        return False
    return True


def _penalty(task: dict, provider: dict) -> float:
    penalty = 0.0
    required_caps = {str(cap).strip().lower() for cap in task.get("required_capabilities", [])}
    penalty += float(len(required_caps - _capabilities(provider)))

    latency_gap = max(0.0, float(provider.get("estimated_latency_ms", 0)) - float(task.get("max_latency_ms", 0)))
    penalty += latency_gap / max(1.0, float(task.get("max_latency_ms", 1)))

    quality_gap = max(0.0, float(task.get("min_quality_score", 0.0)) - float(provider.get("quality_score", 0.0)))
    penalty += quality_gap * 10.0

    max_cost = task.get("max_cost_usd")
    if max_cost is not None:
        cost_gap = max(0.0, float(provider.get("estimated_cost_usd", 0.0)) - float(max_cost))
        penalty += cost_gap * 100.0

    required_privacy = str(task.get("privacy_requirement", "public"))
    actual_privacy = str(provider.get("privacy_tier", "public"))
    if not _privacy_ok(required_privacy, actual_privacy):
        penalty += 5.0

    return penalty


def _sort_key(task: dict, provider: dict):
    feasible = _is_feasible(task, provider)
    privacy_bonus = PRIVACY_ORDER.get(str(provider.get("privacy_tier", "public")), 0)
    if feasible:
        return (
            0,
            float(provider.get("estimated_cost_usd", 0.0)),
            float(provider.get("estimated_latency_ms", 0)),
            -float(provider.get("reliability_score", 0.0)),
            -privacy_bonus,
        )

    return (
        1,
        _penalty(task, provider),
        float(provider.get("estimated_cost_usd", 0.0)),
        float(provider.get("estimated_latency_ms", 0)),
        -float(provider.get("reliability_score", 0.0)),
    )


def agent_main(task: dict) -> dict:
    providers = list(task.get("candidate_providers", []))
    if not providers:
        raise ValueError("Task does not include any candidate providers.")

    ranked = sorted(providers, key=lambda provider: _sort_key(task, provider))
    selected = ranked[0]
    feasible = _is_feasible(task, selected)
    fallbacks = [
        provider.get("provider_id", "")
        for provider in ranked[1:3]
        if provider.get("provider_id", "") and provider.get("provider_id", "") != selected.get("provider_id", "")
    ]

    rationale = (
        "Selected the cheapest feasible route that satisfies latency, quality, "
        "capability, and privacy constraints."
        if feasible
        else "No feasible route was available, so selected the least-bad fallback route."
    )

    return {
        "task_id": task["task_id"],
        "selected_provider_id": selected["provider_id"],
        "fallback_provider_ids": fallbacks,
        "expected_cost_usd": float(selected["estimated_cost_usd"]),
        "expected_latency_ms": int(selected["estimated_latency_ms"]),
        "expected_quality_score": float(selected["quality_score"]),
        "expected_reliability_score": float(selected["reliability_score"]),
        "confidence": 0.9 if feasible else 0.45,
        "rationale": rationale,
        "policy_tags": ["cost-first", "feasible-first"] if feasible else ["best-effort"],
        "agent_name": "sluice-baseline-router",
        "agent_version": "0.1.0",
    }
