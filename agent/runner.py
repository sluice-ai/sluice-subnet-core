#!/usr/bin/env python3
import importlib.util
import json
import os
import sys
import threading
import traceback
from pathlib import Path


MINER_ROOT = Path("/miner_agent")
TASK_FILE = Path("/challenge/task.json")
AGENT_RELATIVE_PATH = os.getenv("AGENT_RELATIVE_PATH", "agent.py")
RUNNER_DEADLINE_S = int(os.getenv("RUNNER_DEADLINE_S", "45"))
AGENT_SEARCH_PATHS = ("agent.py", "agent/agent.py", "router.py", "src/agent.py")


def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, flush=True, **kwargs)


def resolve_agent_path() -> Path:
    preferred = MINER_ROOT / AGENT_RELATIVE_PATH
    if preferred.exists():
        return preferred

    for relative_path in AGENT_SEARCH_PATHS:
        candidate = MINER_ROOT / relative_path
        if candidate.exists():
            return candidate

    raise FileNotFoundError("No routing agent found in miner repository.")


def load_agent():
    agent_path = resolve_agent_path()
    spec = importlib.util.spec_from_file_location("sluice_router_agent", str(agent_path))
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:  # pragma: no cover - hard to trigger meaningfully in unit tests
        raise ImportError(f"agent.py failed to import: {exc}") from exc

    if not hasattr(module, "agent_main"):
        raise AttributeError("agent_main(task) not found in routing agent.")
    return module


def load_task() -> dict:
    if not TASK_FILE.exists():
        raise FileNotFoundError(f"Missing benchmark task file at {TASK_FILE}")
    return json.loads(TASK_FILE.read_text(encoding="utf-8"))


class _AgentThread(threading.Thread):
    def __init__(self, module, task):
        super().__init__(daemon=True)
        self.module = module
        self.task = task
        self.result = None
        self.error = None

    def run(self):
        try:
            self.result = self.module.agent_main(self.task)
        except Exception as exc:  # pragma: no cover - error path only
            self.error = (type(exc).__name__, str(exc), traceback.format_exc())


def validate_result(result: dict, task: dict) -> dict:
    if not isinstance(result, dict):
        raise TypeError(f"agent_main() must return a dict, got {type(result).__name__}")

    normalized = dict(result)
    normalized.setdefault("task_id", task.get("task_id", "unknown"))
    normalized.setdefault("fallback_provider_ids", [])
    normalized.setdefault("policy_tags", [])
    normalized.setdefault("agent_name", "sluice-router")
    normalized.setdefault("agent_version", "0.1.0")

    required_fields = (
        "task_id",
        "selected_provider_id",
        "expected_cost_usd",
        "expected_latency_ms",
        "expected_quality_score",
        "expected_reliability_score",
        "confidence",
        "rationale",
    )
    missing = [field for field in required_fields if field not in normalized]
    if missing:
        raise KeyError(f"agent_main() missing required fields: {missing}")

    normalized["selected_provider_id"] = str(normalized["selected_provider_id"]).strip()
    normalized["fallback_provider_ids"] = [str(value) for value in normalized["fallback_provider_ids"]]
    normalized["expected_cost_usd"] = float(normalized["expected_cost_usd"])
    normalized["expected_latency_ms"] = int(normalized["expected_latency_ms"])
    normalized["expected_quality_score"] = float(normalized["expected_quality_score"])
    normalized["expected_reliability_score"] = float(normalized["expected_reliability_score"])
    normalized["confidence"] = float(normalized["confidence"])
    normalized["rationale"] = str(normalized["rationale"]).strip()
    normalized["policy_tags"] = [str(value) for value in normalized["policy_tags"]]
    normalized["agent_name"] = str(normalized["agent_name"]).strip()
    normalized["agent_version"] = str(normalized["agent_version"]).strip()

    if not normalized["selected_provider_id"]:
        raise ValueError("selected_provider_id must not be empty")
    if normalized["expected_cost_usd"] < 0 or normalized["expected_latency_ms"] < 0:
        raise ValueError("Expected cost and latency must be non-negative")
    for field_name in ("expected_quality_score", "expected_reliability_score", "confidence"):
        value = normalized[field_name]
        if not 0.0 <= value <= 1.0:
            raise ValueError(f"{field_name} must be between 0.0 and 1.0")
    if not normalized["rationale"]:
        raise ValueError("rationale must not be empty")

    return normalized


def call_agent_with_deadline(module, task: dict) -> dict:
    thread = _AgentThread(module, task)
    thread.start()
    thread.join(RUNNER_DEADLINE_S)

    if thread.is_alive():
        raise TimeoutError(f"agent_main() timed out after {RUNNER_DEADLINE_S}s")
    if thread.error:
        exc_type, exc_msg, _ = thread.error
        raise RuntimeError(f"agent_main() raised {exc_type}: {exc_msg}")

    return validate_result(thread.result, task)


def error_report(task_id: str, reason: str) -> dict:
    return {
        "task_id": task_id,
        "selected_provider_id": "",
        "fallback_provider_ids": [],
        "expected_cost_usd": 0.0,
        "expected_latency_ms": 0,
        "expected_quality_score": 0.0,
        "expected_reliability_score": 0.0,
        "confidence": 0.0,
        "rationale": reason,
        "policy_tags": ["runner-error"],
        "agent_name": "sluice-runner",
        "agent_version": "0.1.0",
    }


def main():
    task_id = "unknown"
    try:
        task = load_task()
        task_id = task.get("task_id", "unknown")
        agent = load_agent()
        result = call_agent_with_deadline(agent, task)
        print(json.dumps(result), flush=True)
    except Exception as exc:  # pragma: no cover - exercised in container failures
        eprint(f"[runner] {type(exc).__name__}: {exc}")
        eprint(traceback.format_exc())
        print(json.dumps(error_report(task_id, f"{type(exc).__name__}: {exc}")), flush=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
