# Sluice Subnet

Sluice is a Bittensor subnet for AI routing. Miners compete by publishing routing agents, and validators benchmark those agents against routing tasks that encode cost, latency, quality, and privacy constraints.

The repo is now focused fully on the Sluice routing brief:

- miners register a router repo instead of returning a one-off answer
- validators sandbox and execute the router against benchmark tasks
- rewards favor the cheapest feasible route that still satisfies task requirements
- the validator works out of the box with bundled local benchmark tasks, while still supporting a remote task API later

## Architecture

Core pieces:

- `neurons/miner.py`: miner neuron that advertises a router repository URL and capability metadata
- `neurons/validator.py`: validator neuron that builds the sandbox image and scores miner routers
- `sluice_subnet/protocol.py`: synapse definition used between miners and validators
- `sluice/benchmark_client.py`: local-first benchmark task loader with optional remote API support
- `sluice/scorer.py`: deterministic routing scorer
- `sluice/sandbox.py`: validator-side sandbox that clones and executes miner routing agents
- `agent/runner.py`: minimal runtime baked into the validator sandbox image
- `agent/agent.py`: sample router agent you can use as a first-party baseline

## Competitive Approach

The fastest way to become competitive on a routing subnet is to score real routing policies, not self-reported claims. This scaffold does that by:

- letting miners ship routing logic as code
- evaluating that code against the exact same task payload on the validator side
- enforcing a safety boundary with a read-only, no-network sandbox
- making reward primarily cost-driven, with smaller bonuses for latency headroom, reliability, privacy fit, calibration, and valid fallbacks

This matches the Sluice idea from your PDF: validators benchmark proposed routes and reward the cheapest route that still meets requirements.

## Quick Start

1. Install dependencies.

```bash
python -m pip install -r requirements.txt
```

2. Copy `.env.example` into `.env.miner` and `.env.validator`.

3. Set `ROUTER_REPO_URL` in `.env.miner`.

For local single-machine testing, `file://` works. The validator sandbox will also accept repos where the agent lives at either `agent.py` in the repo root or `agent/agent.py`, so you can point a first-party miner at this repo during bootstrap if needed.

4. Run the miner and validator.

```bash
python neurons/miner.py --netuid <your-netuid>
python neurons/validator.py --netuid <your-netuid>
```

## Miner Contract

A miner advertises a git repo containing a routing agent with:

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

## Local Benchmarks

If `SLUICE_TASK_API` is unset, validators use bundled synthetic routing tasks from `sluice/benchmarks/tasks.json`. That means you can boot the subnet and test miner/validator behavior before you stand up any benchmark API.

## Notes

- Docker is required on the validator machine because the validator executes miner routing agents in a sandbox.
- Set `SLUICE_SKIP_SANDBOX_BUILD=1` if you only want to run import-level or unit-test validation without building the Docker image.
