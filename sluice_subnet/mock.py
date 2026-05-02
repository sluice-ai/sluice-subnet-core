import asyncio
import random
import time
from typing import List

import bittensor as bt


class MockSubtensor(bt.MockSubtensor):
    def __init__(self, netuid, n=16, wallet=None, network="mock"):
        super().__init__(network=network)

        if not self.subnet_exists(netuid):
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


class MockMetagraph(bt.Metagraph):
    def __init__(self, netuid=1, network="mock", subtensor=None):
        super().__init__(netuid=netuid, network=network, sync=False)

        if subtensor is not None:
            self.subtensor = subtensor
        self.sync(subtensor=subtensor)

        for axon in self.axons:
            axon.ip = "127.0.0.0"
            axon.port = 8091

        bt.logging.info(f"Metagraph: {self}")
        bt.logging.info(f"Axons: {self.axons}")


class MockDendrite(bt.Dendrite):
    def __init__(self, wallet):
        super().__init__(wallet)

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
                s = synapse.copy()
                s = self.preprocess_synapse_for_request(axon, s, timeout)
                process_time = random.random()
                if process_time < timeout:
                    s.dendrite.process_time = str(time.time() - start_time)
                    s.router_repo_url = f"https://example.com/mock-router-{i}.git"
                    s.router_version = "mock"
                    s.dendrite.status_code = 200
                    s.dendrite.status_message = "OK"
                else:
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
