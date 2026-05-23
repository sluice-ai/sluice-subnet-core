from __future__ import annotations

from typing import Any, Optional

import bittensor as bt

from sluice.models import RouterArtifactManifest


def manifest_from_synapse(
    synapse: Any | None,
) -> Optional[RouterArtifactManifest]:
    if synapse is None:
        return None
    if not synapse.router_manifest_json:
        bt.logging.warning("Miner response missing router_manifest_json; skipping legacy response.")
        return None

    try:
        return RouterArtifactManifest.model_validate_json(synapse.router_manifest_json)
    except Exception as exc:
        bt.logging.warning(f"Failed to parse router manifest from miner response: {exc}")
        return None
