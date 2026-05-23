import numpy as np

from sluice.models import RoutingExecutionReport, RoutingTask
from sluice.scorer import reference_provider, score_one
from sluice.benchmarks.model_benchmarks import get_model_benchmark
from sluice_subnet.validator.reward import get_rewards


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


def test_score_rewards_quality_and_latency_centric_route():
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

    # Under new weights: 50% Quality, 25% Cost, 15% Latency, 10% Reliability
    # premium score: 0.5*0.9 + 0.25*(0.003/0.009) + 0.15*1.0 + 0.10*0.97 = 0.780333
    # cheap score: 0.5*0.74 + 0.25*1.0 + 0.15*0.0 + 0.10*0.88 = 0.708
    assert score_one(premium, TASK) > score_one(best, TASK) > 0.0


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


def test_empty_reward_batch_is_safe():
    rewards = get_rewards(None, [], TASK)

    assert rewards.size == 0
    assert rewards.dtype == np.float32


def test_model_benchmarks_code_vs_text():
    # Chat workload: should return MMLU score
    llama_chat = get_model_benchmark("llama-3.3-70b", workload_type="chat")
    assert llama_chat == 0.860

    # Code workload: should return a blend of SWE-bench and HumanEval (0.5 * 0.23 + 0.5 * 0.80 = 0.515)
    llama_code = get_model_benchmark("llama-3.3-70b", workload_type="code")
    assert llama_code == 0.515

    # Codegen capability fallback: should return code blend
    llama_capability = get_model_benchmark("llama-3.3-70b", workload_type="chat", required_capabilities=["codegen"])
    assert llama_capability == 0.515


def test_model_benchmarks_fallback_behavior():
    # Unknown model with no fallback: should return defaults
    unknown_no_fallback = get_model_benchmark("completely-unknown-model-xyz", workload_type="chat")
    assert unknown_no_fallback == 0.700

    # Unknown model with fallback: should return fallback
    unknown_with_fallback = get_model_benchmark("completely-unknown-model-xyz", workload_type="chat", fallback_score=0.85)
    assert unknown_with_fallback == 0.85
