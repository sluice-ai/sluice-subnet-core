import importlib.util
import json
from pathlib import Path


RUNNER_PATH = Path(__file__).resolve().parent.parent / "agent" / "runner.py"
SAMPLE_AGENT_PATH = Path(__file__).resolve().parent.parent / "agent" / "agent.py"


def load_runner_module():
    spec = importlib.util.spec_from_file_location("sluice_runner", RUNNER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sample_task() -> dict:
    return {
        "task_id": "unit-test-task",
        "workload_type": "chat",
        "objective": "Select the cheapest feasible provider.",
        "prompt_tokens": 1000,
        "completion_tokens": 300,
        "max_latency_ms": 900,
        "min_quality_score": 0.7,
        "privacy_requirement": "public",
        "max_cost_usd": 0.01,
        "required_capabilities": ["json-mode"],
        "candidate_providers": [
            {
                "provider_id": "cheap-feasible",
                "provider_kind": "bittensor_subnet",
                "model_id": "sn-alpha",
                "estimated_cost_usd": 0.003,
                "estimated_latency_ms": 600,
                "quality_score": 0.74,
                "reliability_score": 0.88,
                "privacy_tier": "internal",
                "capabilities": ["json-mode"]
            },
            {
                "provider_id": "premium-fallback",
                "provider_kind": "external_api",
                "model_id": "premium-1",
                "estimated_cost_usd": 0.007,
                "estimated_latency_ms": 500,
                "quality_score": 0.9,
                "reliability_score": 0.97,
                "privacy_tier": "public",
                "capabilities": ["json-mode", "function-calling"]
            }
        ]
    }


def test_runner_executes_sample_agent(tmp_path):
    runner = load_runner_module()

    miner_root = tmp_path / "miner"
    miner_root.mkdir()
    (miner_root / "agent.py").write_text(SAMPLE_AGENT_PATH.read_text(encoding="utf-8"), encoding="utf-8")

    challenge_dir = tmp_path / "challenge"
    challenge_dir.mkdir()
    (challenge_dir / "task.json").write_text(json.dumps(sample_task()), encoding="utf-8")

    runner.MINER_ROOT = miner_root
    runner.TASK_FILE = challenge_dir / "task.json"
    runner.AGENT_RELATIVE_PATH = "agent.py"

    agent_module = runner.load_agent()
    task = runner.load_task()
    result = runner.call_agent_with_deadline(agent_module, task)

    assert result["selected_provider_id"] == "cheap-feasible"
    assert result["fallback_provider_ids"] == ["premium-fallback"]
    assert result["confidence"] > 0.5
