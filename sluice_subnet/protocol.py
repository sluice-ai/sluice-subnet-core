import typing

import bittensor as bt
from pydantic import Field


class RoutePlanSynapse(bt.Synapse):
    task_json: str = Field(
        default="",
        description="A JSON-serialized Sluice routing benchmark task.",
    )
    router_manifest_json: typing.Optional[str] = Field(
        default=None,
        description="JSON-serialized artifact manifest for the miner's routing policy.",
    )
    router_repo_url: typing.Optional[str] = Field(
        default=None,
        description="Deprecated legacy router repository URL.",
    )
    router_version: typing.Optional[str] = Field(
        default=None,
        description="Human-readable version string for the miner router.",
    )
    router_summary: typing.Optional[str] = Field(
        default=None,
        description="Short description of the miner's routing policy.",
    )
    router_capabilities: list[str] = Field(
        default_factory=list,
        description="Capabilities the router claims to support.",
    )
    supported_privacy_tiers: list[str] = Field(
        default_factory=list,
        description="Privacy tiers the router claims to support.",
    )

    def deserialize(self) -> typing.Optional[str]:
        return self.router_manifest_json or self.router_repo_url
