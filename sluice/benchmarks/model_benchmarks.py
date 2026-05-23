import re
from typing import Optional

# Standard LLM benchmarks: MMLU for text-based, SWE-bench & HumanEval for code-based
MODEL_BENCHMARKS = {
    "claude-sonnet-4": {
        "mmlu": 0.887,
        "swe_bench": 0.490,
        "human_eval": 0.920,
    },
    "claude-3-5-sonnet": {
        "mmlu": 0.887,
        "swe_bench": 0.490,
        "human_eval": 0.920,
    },
    "gpt-4.1-mini": {
        "mmlu": 0.820,
        "swe_bench": 0.280,
        "human_eval": 0.860,
    },
    "gpt-4o-mini": {
        "mmlu": 0.820,
        "swe_bench": 0.280,
        "human_eval": 0.860,
    },
    "gpt-4o": {
        "mmlu": 0.887,
        "swe_bench": 0.380,
        "human_eval": 0.902,
    },
    "llama-3.3-70b": {
        "mmlu": 0.860,
        "swe_bench": 0.230,
        "human_eval": 0.800,
    },
    "groq-llama-70b": {
        "mmlu": 0.860,
        "swe_bench": 0.230,
        "human_eval": 0.800,
    },
    "llama-3.1-8b": {
        "mmlu": 0.684,
        "swe_bench": 0.100,
        "human_eval": 0.650,
    },
    "groq-llama-8b": {
        "mmlu": 0.684,
        "swe_bench": 0.100,
        "human_eval": 0.650,
    },
    "sn-reasoner-ops": {
        "mmlu": 0.830,
        "swe_bench": 0.300,
        "human_eval": 0.840,
    },
    "secure-agent-route-v1": {
        "mmlu": 0.810,
        "swe_bench": 0.220,
        "human_eval": 0.780,
    },
    "tee-agent-route": {
        "mmlu": 0.810,
        "swe_bench": 0.220,
        "human_eval": 0.780,
    },
    "secure-codeguard-v1": {
        "mmlu": 0.820,
        "swe_bench": 0.350,
        "human_eval": 0.880,
    },
    "tee-codeguard": {
        "mmlu": 0.820,
        "swe_bench": 0.350,
        "human_eval": 0.880,
    },
    "sn-tee-code-beta": {
        "mmlu": 0.800,
        "swe_bench": 0.320,
        "human_eval": 0.850,
    },
    "confi-bt-tee": {
        "mmlu": 0.800,
        "swe_bench": 0.320,
        "human_eval": 0.850,
    },
    "sn-code-beta": {
        "mmlu": 0.750,
        "swe_bench": 0.250,
        "human_eval": 0.780,
    },
    "bt-code-beta": {
        "mmlu": 0.750,
        "swe_bench": 0.250,
        "human_eval": 0.780,
    },
    "sn-chat-alpha": {
        "mmlu": 0.750,
        "swe_bench": 0.120,
        "human_eval": 0.700,
    },
    "bt-text-alpha": {
        "mmlu": 0.750,
        "swe_bench": 0.120,
        "human_eval": 0.700,
    },
}


def lookup_model_stats(model_id: str) -> Optional[dict[str, float]]:
    normalized = model_id.lower().strip()
    
    # Direct lookup
    if normalized in MODEL_BENCHMARKS:
        return MODEL_BENCHMARKS[normalized]
    
    # Substring / key matching
    for pattern, stats in MODEL_BENCHMARKS.items():
        if pattern in normalized or normalized in pattern:
            return stats
            
    # Wildcard fallbacks
    if "claude" in normalized:
        return MODEL_BENCHMARKS["claude-sonnet-4"]
    if "gpt-4" in normalized:
        return MODEL_BENCHMARKS["gpt-4o-mini"]
    if "llama" in normalized:
        if "70b" in normalized or "70" in normalized:
            return MODEL_BENCHMARKS["llama-3.3-70b"]
        return MODEL_BENCHMARKS["llama-3.1-8b"]
        
    return None


def get_model_benchmark(
    model_id: str,
    workload_type: str,
    required_capabilities: Optional[list[str]] = None,
    fallback_score: Optional[float] = None,
) -> float:
    """
    Looks up the standard benchmark score of the model based on the workload type.
    - If workload is 'code' or capabilities contain 'codegen', returns a blend of SWE-bench and HumanEval scores.
    - Else, returns the general language model score (MMLU).
    """
    stats = lookup_model_stats(model_id)
    
    if stats is None:
        if fallback_score is not None:
            return fallback_score
        stats = {
            "mmlu": 0.700,
            "swe_bench": 0.150,
            "human_eval": 0.700,
        }
    
    is_code = (workload_type.lower() == "code") or (
        required_capabilities is not None and "codegen" in [c.lower() for c in required_capabilities]
    )
    
    if is_code:
        # Use a balanced blend of HumanEval (unit testing) and SWE-bench (software engineering resolving real issues)
        swe = stats.get("swe_bench", 0.15)
        he = stats.get("human_eval", 0.70)
        score = 0.5 * swe + 0.5 * he
    else:
        score = stats.get("mmlu", 0.70)
        
    return score
