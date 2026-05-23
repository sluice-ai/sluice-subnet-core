from __future__ import annotations

import asyncio
import os
from pathlib import Path
import sys

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sluice.benchmark_client import BenchmarkClient
from sluice.router import load_manifest_file
from sluice.sandbox import SandboxRunner
from sluice.scorer import reference_provider, score_one
from sluice.validation import manifest_from_synapse
from sluice_subnet.protocol import RoutePlanSynapse

async def main() -> None:
    load_dotenv(ROOT / ".env.miner")
    load_dotenv(ROOT / ".env.validator")

    manifest_path = os.getenv("ROUTER_MANIFEST_PATH", "").strip() or os.getenv(
        "SLUICE_MOCK_ROUTER_MANIFEST_PATH", ""
    ).strip()
    if not manifest_path:
        raise EnvironmentError(
            "Set ROUTER_MANIFEST_PATH or SLUICE_MOCK_ROUTER_MANIFEST_PATH before running the smoke flow."
        )

    manifest = load_manifest_file(manifest_path)
    client = BenchmarkClient()
    task = await client.fetch_random_task()
    baseline = reference_provider(task)

    synapse = RoutePlanSynapse(
        task_json=task.model_dump_json(),
        router_manifest_json=manifest.model_dump_json(),
        router_version=manifest.router_version,
        router_summary=manifest.description,
        router_capabilities=manifest.supported_capabilities,
        supported_privacy_tiers=manifest.supported_privacy_tiers,
    )

    resolved_manifest = manifest_from_synapse(synapse)
    if resolved_manifest is None:
        raise RuntimeError("Failed to resolve router manifest from synapse.")

    os.environ["SLUICE_LOCAL_DEV_EXECUTION"] = "1"
    runner = SandboxRunner()
    reports = await runner.run_all([resolved_manifest], task)
    report = reports[0]
    score = score_one(report, task)

    print(f"task_id={task.task_id}")
    print(f"baseline_provider={baseline.provider_id if baseline else 'none'}")
    print(f"selected_provider={report.selected_provider_id if report else 'none'}")
    print(f"score={score:.6f}")
    print(f"report={report.model_dump(mode='json') if report else None}")

    await client.close()


if __name__ == "__main__":
    asyncio.run(main())
