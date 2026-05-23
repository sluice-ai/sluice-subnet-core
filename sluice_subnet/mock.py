import asyncio
import json
import os
import random
import time
from typing import List

import bittensor as bt

from sluice.models import RouterArtifactFormat, RouterArtifactManifest
from sluice.router import load_manifest_file


class MockSubtensor(bt.MockSubtensor):
    def __init__(self, netuid, n=16, wallet=None, network="mock"):
        super().__init__(network=network)

        networks_added = self.chain_state["SubtensorModule"]["NetworksAdded"]
        if netuid not in networks_added:
            self.create_subnet(netuid)

        if wallet is not None:
            self.force_register_neuron(
                netuid=netuid,
                hotkey_ss58=wallet.hotkey.ss58_address,
                coldkey_ss58=wallet.coldkeypub.ss58_address,
                stake=100000,
                balance=100000,
            )

        for i in range(1, n + 1):
            self.force_register_neuron(
                netuid=netuid,
                hotkey_ss58=f"miner-hotkey-{i}",
                coldkey_ss58="mock-coldkey",
                stake=100000,
                balance=100000,
            )

    def neuron_for_uid_lite(self, uid: int, netuid: int, block=None):
        if uid is None:
            return bt.NeuronInfoLite.get_null_neuron()

        if block is not None and self.block_number < block:
            raise Exception("Cannot query block in the future")
        block = self.block_number if block is None else block

        if netuid not in self.chain_state["SubtensorModule"]["NetworksAdded"]:
            return None

        neuron_info = self._neuron_subnet_exists(uid, netuid, block)
        if neuron_info is None:
            return None

        return bt.NeuronInfoLite(
            hotkey=neuron_info.hotkey,
            coldkey=neuron_info.coldkey,
            uid=neuron_info.uid,
            netuid=neuron_info.netuid,
            active=neuron_info.active,
            stake=neuron_info.stake,
            stake_dict=neuron_info.stake_dict,
            total_stake=neuron_info.total_stake,
            emission=neuron_info.emission,
            incentive=neuron_info.incentive,
            consensus=neuron_info.consensus,
            validator_trust=neuron_info.validator_trust,
            dividends=neuron_info.dividends,
            last_update=neuron_info.last_update,
            validator_permit=neuron_info.validator_permit,
            prometheus_info=neuron_info.prometheus_info,
            axon_info=neuron_info.axon_info,
            is_null=neuron_info.is_null,
        )


class MockMetagraph(bt.Metagraph):
    def __init__(self, netuid=1, network="mock", subtensor=None):
        super().__init__(netuid=netuid, network=network, sync=False)

        if subtensor is not None:
            self.subtensor = subtensor
        self.sync(subtensor=subtensor, lite=True)

        for axon in self.axons:
            axon.ip = "127.0.0.0"
            axon.port = 8091

        bt.logging.info(f"Metagraph: {self}")
        bt.logging.info(f"Axons: {self.axons}")

    def sync(self, block=None, lite=True, subtensor=None):
        subtensor = self._initialize_subtensor(subtensor=subtensor)
        if block is None:
            block = subtensor.get_current_block()

        self._assign_neurons(block, lite, subtensor)
        self._set_metagraph_attributes(block)
        if not lite:
            self._set_weights_and_bonds(subtensor=subtensor, block=block)
        self._get_all_stakes_from_chain(block=block)
        return self


class MockDendrite(bt.Dendrite):
    def __init__(self, wallet):
        super().__init__(wallet)

    @staticmethod
    def _mock_manifest(i: int) -> RouterArtifactManifest:
        manifest_path = os.getenv("SLUICE_MOCK_ROUTER_MANIFEST_PATH", "").strip()
        if manifest_path:
            return load_manifest_file(manifest_path)

        artifact_uri = os.getenv("SLUICE_MOCK_ROUTER_ARTIFACT_URI", "").strip()
        artifact_sha256 = os.getenv("SLUICE_MOCK_ROUTER_ARTIFACT_SHA256", "").strip().lower()
        if artifact_uri and artifact_sha256:
            return RouterArtifactManifest(
                artifact_uri=artifact_uri,
                sha256=artifact_sha256,
                artifact_format=RouterArtifactFormat(
                    os.getenv("SLUICE_MOCK_ROUTER_ARTIFACT_FORMAT", RouterArtifactFormat.tar_gz.value)
                ),
                entrypoint_path=os.getenv("SLUICE_MOCK_ROUTER_ENTRYPOINT_PATH", "agent.py").strip(),
                entrypoint_callable=os.getenv(
                    "SLUICE_MOCK_ROUTER_ENTRYPOINT_CALLABLE", "agent_main"
                ).strip(),
                router_name=os.getenv("SLUICE_MOCK_ROUTER_NAME", "mock-router").strip(),
                router_version=os.getenv("SLUICE_MOCK_ROUTER_VERSION", "mock").strip(),
                supported_capabilities=["json-mode"],
                supported_privacy_tiers=["public"],
                description="Mock router artifact from environment.",
            )

        return RouterArtifactManifest(
            artifact_uri=f"https://example.com/mock-router-{i}.tar.gz",
            sha256="a" * 64,
            artifact_format=RouterArtifactFormat.tar_gz,
            entrypoint_path="agent.py",
            entrypoint_callable="agent_main",
            router_name=f"mock-router-{i}",
            router_version="mock",
            supported_capabilities=["json-mode"],
            supported_privacy_tiers=["public"],
            description="Mock router artifact.",
        )

    async def forward(
        self,
        axons: List[bt.Axon],
        synapse: bt.Synapse = bt.Synapse(),
        timeout: float = 12,
        deserialize: bool = True,
        run_async: bool = True,
        streaming: bool = False,
    ):
        if streaming:
            raise NotImplementedError("Streaming not implemented yet.")

        async def query_all_axons(streaming: bool):
            async def single_axon_response(i, axon):
                start_time = time.time()
                if hasattr(synapse, "model_copy"):
                    s = synapse.model_copy(deep=True)
                else:
                    s = synapse.copy()
                s = self.preprocess_synapse_for_request(axon, s, timeout)
                process_time = random.random()
                if process_time < timeout:
                    s.dendrite.process_time = str(time.time() - start_time)
                    manifest = self._mock_manifest(i)
                    s.router_manifest_json = manifest.model_dump_json()
                    s.router_repo_url = manifest.artifact_uri
                    s.router_version = manifest.router_version
                    s.dendrite.status_code = 200
                    s.dendrite.status_message = "OK"
                else:
                    s.router_manifest_json = None
                    s.router_repo_url = None
                    s.dendrite.status_code = 408
                    s.dendrite.status_message = "Timeout"

                if deserialize:
                    return s.deserialize()
                return s

            return await asyncio.gather(
                *(single_axon_response(i, target_axon) for i, target_axon in enumerate(axons))
            )

        return await query_all_axons(streaming)

    def __str__(self) -> str:
        return "MockDendrite({})".format(self.keypair.ss58_address)
