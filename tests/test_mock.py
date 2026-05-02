import pytest

bt = pytest.importorskip("bittensor")

from sluice_subnet.protocol import RoutePlanSynapse


def test_route_plan_synapse_deserialize():
    synapse = RoutePlanSynapse(
        task_json="{}",
        router_repo_url="https://example.com/router.git",
    )

    assert synapse.deserialize() == "https://example.com/router.git"
