import asyncio
import importlib
import sys
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("bittensor")

ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = ROOT / "dist" / "router" / "sluice-baseline-router-0.1.0.manifest.json"


def reload_module(module_name: str):
    return importlib.reload(importlib.import_module(module_name))


def test_miner_boots_with_subclass_defaults(monkeypatch, tmp_path):
    monkeypatch.setenv("BT_NO_PARSE_CLI_ARGS", "false")
    monkeypatch.setenv("ROUTER_MANIFEST_PATH", str(MANIFEST_PATH))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "miner-test",
            "--mock",
            "--netuid",
            "101",
            "--wallet.name",
            "test_miner_wallet",
            "--wallet.hotkey",
            "miner_hotkey",
            "--logging.logging_dir",
            str(tmp_path),
        ],
    )

    miner_module = reload_module("neurons.miner")
    miner = miner_module.Miner()

    assert miner.config.neuron.name == "miner"
    assert miner.router_manifest.router_name == "sluice-baseline-router"


def test_validator_forward_updates_scores_in_mock_mode(monkeypatch, tmp_path):
    monkeypatch.setenv("BT_NO_PARSE_CLI_ARGS", "false")
    monkeypatch.setenv("SLUICE_SKIP_SANDBOX_BUILD", "1")
    monkeypatch.setenv("SLUICE_LOCAL_DEV_EXECUTION", "1")
    monkeypatch.setenv("ROUTER_MANIFEST_PATH", str(MANIFEST_PATH))
    monkeypatch.setenv("SLUICE_MOCK_ROUTER_MANIFEST_PATH", str(MANIFEST_PATH))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "validator-test",
            "--mock",
            "--netuid",
            "102",
            "--wallet.name",
            "test_validator_wallet",
            "--wallet.hotkey",
            "validator_hotkey",
            "--logging.logging_dir",
            str(tmp_path),
            "--neuron.axon_off",
            "--neuron.disable_set_weights",
            "--neuron.sample_size",
            "4",
        ],
    )

    reload_module("sluice_subnet.validator.forward")
    validator_module = reload_module("neurons.validator")
    validator = validator_module.Validator()

    asyncio.run(validator.forward())

    assert validator.config.neuron.name == "validator"
    assert np.count_nonzero(validator.scores) > 0
