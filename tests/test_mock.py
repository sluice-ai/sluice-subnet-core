import pytest

bt = pytest.importorskip("bittensor")

from sluice.models import RouterArtifactManifest
from sluice_subnet.protocol import RoutePlanSynapse


def test_route_plan_synapse_deserialize():
    manifest = RouterArtifactManifest(
        artifact_uri="https://example.com/router.tar.gz",
        sha256="a" * 64,
        artifact_format="tar.gz",
        entrypoint_path="agent.py",
        entrypoint_callable="agent_main",
        router_name="example-router",
        router_version="1.0.0",
        supported_capabilities=["json-mode"],
        supported_privacy_tiers=["public"],
    )
    synapse = RoutePlanSynapse(
        task_json="{}",
        router_manifest_json=manifest.model_dump_json(),
    )

    assert synapse.deserialize() == manifest.model_dump_json()
