import os
import sys
import time
import typing
from pathlib import Path

import bittensor as bt
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import sluice_subnet
from sluice.models import RoutingTask
from sluice_subnet.base.miner import BaseMinerNeuron

load_dotenv(Path(__file__).resolve().parent.parent / ".env.miner")


class Miner(BaseMinerNeuron):
    def __init__(self, config=None):
        super().__init__(config=config)
        self.router_repo_url = os.getenv("ROUTER_REPO_URL", "").strip()
        if not self.router_repo_url:
            raise EnvironmentError("ROUTER_REPO_URL must be set in .env.miner or the environment.")

        self.router_label = os.getenv("ROUTER_LABEL", "sluice-router").strip()
        self.router_version = os.getenv("ROUTER_VERSION", "0.1.0").strip()
        self.router_summary = os.getenv(
            "ROUTER_SUMMARY",
            "Cost-first feasible routing policy for Sluice tasks.",
        ).strip()
        self.router_capabilities = self._split_env("ROUTER_SUPPORTED_CAPABILITIES")
        self.supported_privacy_tiers = self._split_env("ROUTER_SUPPORTED_PRIVACY_TIERS")

    @staticmethod
    def _split_env(name: str) -> list[str]:
        raw_value = os.getenv(name, "")
        return [item.strip().lower() for item in raw_value.split(",") if item.strip()]

    def _supports_task(self, synapse: sluice_subnet.protocol.RoutePlanSynapse) -> bool:
        if not synapse.task_json:
            return True

        try:
            task = RoutingTask.model_validate_json(synapse.task_json)
        except Exception:
            return True

        required_caps = set(task.required_capabilities)
        privacy_supported = task.privacy_requirement.value in self.supported_privacy_tiers
        return required_caps.issubset(set(self.router_capabilities)) and privacy_supported

    async def forward(
        self, synapse: sluice_subnet.protocol.RoutePlanSynapse
    ) -> sluice_subnet.protocol.RoutePlanSynapse:
        synapse.router_repo_url = self.router_repo_url
        synapse.router_version = self.router_version
        synapse.router_summary = self.router_summary
        synapse.router_capabilities = self.router_capabilities
        synapse.supported_privacy_tiers = self.supported_privacy_tiers
        return synapse

    async def blacklist(
        self, synapse: sluice_subnet.protocol.RoutePlanSynapse
    ) -> typing.Tuple[bool, str]:
        if synapse.dendrite is None or synapse.dendrite.hotkey is None:
            bt.logging.warning("Received request without dendrite metadata.")
            return True, "Missing dendrite or hotkey"

        hotkey = synapse.dendrite.hotkey
        if hotkey not in self.metagraph.hotkeys:
            if self.config.blacklist.allow_non_registered:
                return False, "Allowing non-registered hotkey"
            return True, "Unrecognized hotkey"

        uid = self.metagraph.hotkeys.index(hotkey)
        if self.config.blacklist.force_validator_permit and not self.metagraph.validator_permit[uid]:
            return True, "Non-validator hotkey"

        return False, "Hotkey recognized"

    async def priority(self, synapse: sluice_subnet.protocol.RoutePlanSynapse) -> float:
        if synapse.dendrite is None or synapse.dendrite.hotkey is None:
            return 0.0

        hotkey = synapse.dendrite.hotkey
        if hotkey not in self.metagraph.hotkeys:
            return 0.0

        caller_uid = self.metagraph.hotkeys.index(hotkey)
        base_priority = float(self.metagraph.S[caller_uid])
        capability_bonus = 0.25 if self._supports_task(synapse) else 0.0
        return base_priority + capability_bonus


def main():
    with Miner() as miner:
        while True:
            bt.logging.info(f"Miner running... {time.time()}")
            time.sleep(5)


if __name__ == "__main__":
    main()
