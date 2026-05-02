from sluice.models import RoutingExecutionReport, RoutingTask
from sluice.scorer import reference_provider, score_one


TASK = RoutingTask.model_validate(
    {
        "task_id": "score-task",
        "workload_type": "chat",
        "objective": "Prefer the cheapest feasible route.",
        "prompt_tokens": 1200,
        "completion_tokens": 300,
        "max_latency_ms": 900,
        "min_quality_score": 0.72,
        "privacy_requirement": "public",
        "max_cost_usd": 0.02,
        "required_capabilities": ["json-mode"],
        "candidate_providers": [
            {
                "provider_id": "cheap-feasible",
                "provider_kind": "bittensor_subnet",
                "model_id": "sn-alpha",
                "estimated_cost_usd": 0.003,
                "estimated_latency_ms": 700,
                "quality_score": 0.74,
                "reliability_score": 0.88,
                "privacy_tier": "internal",
                "capabilities": ["json-mode"]
            },
            {
                "provider_id": "premium-feasible",
                "provider_kind": "external_api",
                "model_id": "premium-1",
                "estimated_cost_usd": 0.009,
                "estimated_latency_ms": 500,
                "quality_score": 0.9,
                "reliability_score": 0.97,
                "privacy_tier": "public",
                "capabilities": ["json-mode", "function-calling"]
            },
            {
                "provider_id": "fast-but-infeasible",
                "provider_kind": "external_api",
                "model_id": "fast-1",
                "estimated_cost_usd": 0.002,
                "estimated_latency_ms": 350,
                "quality_score": 0.61,
                "reliability_score": 0.9,
                "privacy_tier": "public",
                "capabilities": ["json-mode"]
            }
        ]
    }
)


def test_reference_provider_picks_cheapest_feasible_route():
    assert reference_provider(TASK).provider_id == "cheap-feasible"


def test_score_rewards_cheapest_feasible_route():
    best = RoutingExecutionReport(
        task_id=TASK.task_id,
        selected_provider_id="cheap-feasible",
        fallback_provider_ids=["premium-feasible"],
        expected_cost_usd=0.003,
        expected_latency_ms=700,
        expected_quality_score=0.74,
        expected_reliability_score=0.88,
        confidence=0.9,
        rationale="Best route.",
    )
    premium = RoutingExecutionReport(
        task_id=TASK.task_id,
        selected_provider_id="premium-feasible",
        fallback_provider_ids=["cheap-feasible"],
        expected_cost_usd=0.009,
        expected_latency_ms=500,
        expected_quality_score=0.9,
        expected_reliability_score=0.97,
        confidence=0.9,
        rationale="More expensive route.",
    )

    assert score_one(best, TASK) > score_one(premium, TASK) > 0.0


def test_infeasible_route_scores_zero():
    infeasible = RoutingExecutionReport(
        task_id=TASK.task_id,
        selected_provider_id="fast-but-infeasible",
        fallback_provider_ids=[],
        expected_cost_usd=0.002,
        expected_latency_ms=350,
        expected_quality_score=0.61,
        expected_reliability_score=0.9,
        confidence=0.9,
        rationale="Cheap but below quality floor.",
    )

    assert score_one(infeasible, TASK) == 0.0
