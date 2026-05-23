# Developer Guide

This guide is for contributors working on the Sluice subnet codebase itself.

## Mental Model

The repo has three main layers:

1. `Router artifact layer`
   `sluice/router/` packages routing code and writes manifests.
2. `Validation layer`
   `sluice/sandbox.py`, `sluice/scorer.py`, and `sluice/benchmark_client.py` evaluate router artifacts.
3. `Subnet runtime layer`
   `neurons/` and `sluice_subnet/` connect the router validation flow to Bittensor miners and validators.

## Repository Layout

- `agent/`: sample router policy plus validator sandbox runtime files
- `neurons/miner.py`: miner runtime that serves a router artifact manifest
- `neurons/validator.py`: validator runtime that samples tasks and scores miners
- `sluice/models.py`: manifest, task, provider, and execution-report models
- `sluice/router/`: artifact builder, cache, digest helpers, and manifest I/O
- `sluice/validation/`: synapse-to-manifest parsing helpers
- `sluice_subnet/protocol.py`: synapse shared by miners and validators
- `sluice_subnet/base/`: generic neuron scaffolding
- `tests/`: focused tests for scoring, router artifacts, runner behavior, and bootstrap flow

## Local Setup

Create a virtualenv and install dependencies:

```bash
python -m venv venv
source venv/bin/activate
python -m pip install -r requirements.txt
```

Copy the sample env files:

```bash
cp .env.example .env.miner
cp .env.example .env.validator
```

## Common Workflows

Build the sample artifact:

```bash
python -m sluice.router.builder \
  --source-dir agent \
  --output-dir dist/router \
  --router-name sluice-baseline-router \
  --router-version 0.1.0 \
  --capability json-mode \
  --privacy-tier public
```

Run the artifact validation smoke test:

```bash
python scripts/smoke_subnet_flow.py
```

Run the focused test suite:

```bash
venv/bin/python -m pytest -q \
  tests/test_neuron_bootstrap.py \
  tests/test_mock.py \
  tests/test_scorer.py \
  tests/test_template_validator.py \
  tests/test_agent_runner.py \
  tests/test_router_artifacts.py
```

Start the nodes locally after subnet registration:

```bash
./start_miner.sh
./start_validator.sh
```

## Where To Change Things

- Add or tighten manifest rules in `sluice/models.py`
- Change router packaging or digest behavior in `sluice/router/`
- Change validator scoring in `sluice/scorer.py`
- Change benchmark task loading in `sluice/benchmark_client.py`
- Change miner-validator message fields in `sluice_subnet/protocol.py`
- Change live validator orchestration in `sluice_subnet/validator/forward.py`
- Change chain-facing neuron behavior in `sluice_subnet/base/`

## Developer Guidelines

- Keep miner and validator behavior aligned with the artifact-first design. Miners announce immutable artifacts; validators benchmark those exact bytes.
- Prefer deterministic validation logic. If a validator decision cannot be reproduced from the task and artifact, it is usually a design smell.
- When changing the synapse, manifest, or execution report format, update both the parser and the tests in the same change.
- Treat the validator sandbox as part of the security boundary. Avoid adding ambient network, file-system, or host access.
- Add regression tests for bug fixes, especially around scoring, manifest parsing, and validator bootstrapping.
- Keep docs in sync with behavior changes. This repo is much easier to operate when README and runbooks match the code.

## Pull Request Checklist

- The change has a clear scope and a short explanation of why it exists.
- Relevant tests pass locally.
- New behavior is covered by tests or a runnable smoke path.
- README or docs were updated if operator behavior changed.
- No secrets, generated caches, or machine-local marker files were added.
