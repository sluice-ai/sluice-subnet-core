from typing import Any, List, Union

import bittensor as bt
from bittensor.subnets import SubnetsAPI

from sluice_subnet.protocol import RoutePlanSynapse


class RoutePlanAPI(SubnetsAPI):
    def __init__(self, wallet: "bt.Wallet", netuid: int = 0):
        super().__init__(wallet)
        self.netuid = netuid
        self.name = "RoutePlanSynapse"

    def prepare_synapse(self, task_json: str) -> RoutePlanSynapse:
        return RoutePlanSynapse(task_json=task_json)

    def process_responses(self, responses: List[Union["bt.Synapse", Any]]) -> List[str]:
        outputs: List[str] = []
        for response in responses:
            if getattr(response, "dendrite", None) and response.dendrite.status_code != 200:
                continue
            if isinstance(response, str):
                outputs.append(response)
            elif isinstance(response, bt.Synapse):
                deserialized = response.deserialize()
                if deserialized:
                    outputs.append(deserialized)
        return outputs
