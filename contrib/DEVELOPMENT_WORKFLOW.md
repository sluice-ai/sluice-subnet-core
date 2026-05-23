# Development Workflow

This document describes the expected day-to-day workflow for changing the Sluice subnet codebase.

## Principles

- Prefer small, reviewable changes over large mixed diffs.
- Keep protocol, tests, and docs aligned.
- Preserve deterministic validator behavior whenever possible.
- Treat security-sensitive code paths such as sandboxing and manifest validation with extra care.

## Typical Flow

1. Start from a clean branch.
2. Choose one scoped change.
3. Implement the code update.
4. Add or update tests.
5. Update docs if operators or contributors will notice the change.
6. Run the relevant verification commands.
7. Open a focused pull request.

## Branching

Suggested branch naming:

- `feature/<short-description>`
- `fix/<short-description>`
- `docs/<short-description>`
- `refactor/<short-description>`

## Expectations By Change Type

Protocol or manifest changes:

- update `sluice/models.py`
- update `sluice_subnet/protocol.py` or manifest parsing as needed
- update tests that cover parsing and bootstrap flow
- document the contract change

Scoring changes:

- update `sluice/scorer.py`
- update or add tests in `tests/test_scorer.py`
- explain the operator impact if miner incentives change materially

Sandbox or artifact changes:

- update `sluice/sandbox.py` or `sluice/router/`
- run the smoke path
- keep validator execution deterministic and restricted

Node boot or chain-facing changes:

- update `neurons/` or `sluice_subnet/base/`
- test miner or validator startup paths
- document any config or registration changes

## Verification

Use the smallest useful verification set for the area you changed.

Focused suite:

```bash
venv/bin/python -m pytest -q \
  tests/test_neuron_bootstrap.py \
  tests/test_mock.py \
  tests/test_scorer.py \
  tests/test_template_validator.py \
  tests/test_agent_runner.py \
  tests/test_router_artifacts.py
```

Smoke flow:

```bash
python scripts/smoke_subnet_flow.py
```

## Documentation Rule

If a change affects any of the following, update docs in the same PR:

- setup steps
- env vars
- miner or validator launch commands
- registration flow
- operator expectations
- router artifact or manifest contracts

## Review Standard

A PR is easier to merge when:

- the purpose is obvious from the title and description
- the code path has tests or a reproducible validation step
- the docs match the code
- unrelated churn is kept out of the diff
