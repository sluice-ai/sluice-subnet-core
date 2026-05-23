# Contributing

Thanks for contributing to Sluice Subnet.

This repository is easier to maintain when code, tests, and operator docs move together. Please treat documentation and regression coverage as part of the feature, not as follow-up work.

## Before You Start

- Read the project [style guide](STYLE.md)
- Read the [development workflow](DEVELOPMENT_WORKFLOW.md)
- Read the repo-level [Developer Guide](../docs/developer_guide.md)

## What We Accept

Good contributions usually fall into one of these categories:

- bug fixes with regression coverage
- improvements to manifest validation, scoring, sandboxing, or neuron flow
- documentation that makes developer or operator behavior clearer
- narrowly scoped refactors that reduce confusion without changing behavior

## Contribution Guidelines

- Keep pull requests focused. One feature, fix, or refactor per PR is ideal.
- Update tests when behavior changes.
- Update docs when operator behavior, config, protocol fields, or runbooks change.
- Do not mix unrelated cleanup with behavior changes unless it clearly improves the same area.
- Avoid adding machine-local files, caches, or generated artifacts unless the repo intentionally tracks them.

## Suggested Local Workflow

1. Create a branch for a single task.
2. Make the code change.
3. Run the focused tests for the area you changed.
4. Run the smoke path if your change touches artifact execution or validator flow.
5. Update documentation if the user-facing or operator-facing behavior changed.
6. Open a PR with a short explanation of what changed and why.

## Validation Commands

Focused regression suite:

```bash
venv/bin/python -m pytest -q \
  tests/test_neuron_bootstrap.py \
  tests/test_mock.py \
  tests/test_scorer.py \
  tests/test_template_validator.py \
  tests/test_agent_runner.py \
  tests/test_router_artifacts.py
```

Artifact smoke path:

```bash
python scripts/smoke_subnet_flow.py
```

## Pull Request Checklist

- the problem or goal is clear
- the diff is scoped to one concern
- tests pass locally
- docs were updated if needed
- commit messages are readable and intentional

## Reporting Bugs

When filing an issue or reporting a bug, include:

- the command you ran
- the network you targeted
- whether you ran miner, validator, or both
- the exact error or stack trace
- the relevant env configuration, with secrets removed
- whether the problem reproduces with the local smoke flow or mock mode
