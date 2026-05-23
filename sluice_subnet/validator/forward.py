from pathlib import Path

import bittensor as bt
from dotenv import load_dotenv

from sluice.benchmark_client import BenchmarkClient
from sluice.sandbox import SandboxRunner
from sluice.scorer import reference_provider
from sluice.validation import manifest_from_synapse
from sluice_subnet.protocol import RoutePlanSynapse
from sluice_subnet.utils.uids import get_random_uids
from sluice_subnet.validator.reward import get_rewards

load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env.validator")

benchmark_client = BenchmarkClient()
sandbox = SandboxRunner()


async def forward(self):
    task = await benchmark_client.fetch_random_task()
    baseline = reference_provider(task)
    miner_uids = get_random_uids(self, k=self.config.neuron.sample_size)
    if len(miner_uids) == 0:
        bt.logging.warning("No available miner UIDs to challenge in this step.")
        return

    bt.logging.info(
        f"Sluice task={task.task_id} workload={task.workload_type} "
        f"providers={len(task.candidate_providers)} "
        f"baseline={baseline.provider_id if baseline else 'none'} "
        f"sample_size={len(miner_uids)}"
    )

    responses = await self.dendrite(
        axons=[self.metagraph.axons[uid] for uid in miner_uids],
        synapse=RoutePlanSynapse(task_json=task.model_dump_json()),
        deserialize=False,
        timeout=self.config.neuron.timeout,
    )

    manifests = [manifest_from_synapse(response) for response in responses]
    manifest_count = sum(1 for manifest in manifests if manifest is not None)
    bt.logging.info(
        f"Sluice miner_responses={len(responses)} valid_manifests={manifest_count}"
    )
    reports = await sandbox.run_all(manifests=manifests, task=task)
    rewards = get_rewards(self, reports=reports, task=task)

    bt.logging.info(f"Sluice rewards={rewards.tolist()}")
    self.update_scores(rewards, miner_uids)
