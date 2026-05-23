# Sluice Subnet

Sluice is a Bittensor subnet for competitive AI routing.

This repository is the subnet control plane:

- miners publish pinned router artifacts plus metadata
- validators fetch, verify, sandbox, and score those artifacts
- validator weights drive miner incentives and validator dividends
- live customer traffic is expected to live in a separate serving system

## What Lives Here

- `neurons/`: miner and validator entrypoints
- `sluice/`: router artifact, sandbox, benchmark, and scoring logic
- `sluice_subnet/`: shared subnet framework, protocol, and mock tooling
- `agent/`: sample router policy and sandbox runner image
- `tests/`: regression tests for the artifact and scoring flow
- `docs/`: developer and operator runbooks

## Documentation Map

- [Developer Guide](docs/developer_guide.md)
- [Miner and Validator Guide](docs/miner_validator_guide.md)
- [Run on Staging / Local Chain](docs/running_on_staging.md)
- [Run on Testnet](docs/running_on_testnet.md)
- [Run on Mainnet](docs/running_on_mainnet.md)
- [Operating a Sluice-like App](docs/operating_a_sluice_like_app.md)

## Quick Start

Install dependencies:

```bash
python -m pip install -r requirements.txt
```

Prepare local env files:

```bash
cp .env.example .env.miner
cp .env.example .env.validator
```

Build the sample router artifact:

```bash
python -m sluice.router.builder \
  --source-dir agent \
  --output-dir dist/router \
  --router-name sluice-baseline-router \
  --router-version 0.1.0 \
  --capability json-mode \
  --privacy-tier public \
  --description "Baseline local router artifact for Sluice."
```

Point the miner at the manifest:

```bash
export ROUTER_MANIFEST_PATH="$(pwd)/dist/router/sluice-baseline-router-0.1.0.manifest.json"
```

Run the local smoke flow without Docker or live chain registration:

```bash
python scripts/smoke_subnet_flow.py
```

Run the subnet processes:

```bash
python neurons/miner.py --netuid <your-netuid>
python neurons/validator.py --netuid <your-netuid>
```

## Subnet Flow

1. A miner builds a router artifact from private source code.
2. The miner publishes a manifest with the artifact URI, digest, entrypoint, version, capabilities, and privacy tiers.
3. A validator samples hidden routing tasks.
4. The validator queries miners for manifests.
5. The validator downloads or resolves the exact artifact bytes, verifies the digest, and caches the artifact.
6. The validator executes the router in the sandbox and scores the result.
7. The validator updates miner weights on-chain.

The core design decision is:

`validators benchmark exact artifact bytes, not moving repo heads`

## Router Contract

Each router artifact must expose a callable such as:

```python
def agent_main(task: dict) -> dict:
    ...
```

The returned dict must include:

- `task_id`
- `selected_provider_id`
- `fallback_provider_ids`
- `expected_cost_usd`
- `expected_latency_ms`
- `expected_quality_score`
- `expected_reliability_score`
- `confidence`
- `rationale`

Optional metadata fields:

- `agent_name`
- `agent_version`
- `policy_tags`

## Manifest Contract

The announced router manifest includes:

- `artifact_uri`
- `sha256`
- `artifact_format`
- `entrypoint_path`
- `entrypoint_callable`
- `router_name`
- `router_version`
- `supported_capabilities`
- `supported_privacy_tiers`
- `description`

See [agent/router_manifest.template.json](agent/router_manifest.template.json).

## Notes

- Docker is required on validator machines for real sandbox execution.
- Validators cache artifacts under `SLUICE_ARTIFACT_CACHE_DIR` or `~/.cache/sluice/router-artifacts`.
- Bundled benchmark tasks live in `sluice/benchmarks/tasks.json` and are used when `SLUICE_TASK_API` is unset.
- `GEMINI_API_KEY` is optional and is not used by validator benchmarking in this repository.
