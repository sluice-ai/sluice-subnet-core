#!/usr/bin/env bash
set -euo pipefail

export BT_NO_PARSE_CLI_ARGS=false

source venv/bin/activate

NETUID="${NETUID:-476}"
WALLET_NAME="${WALLET_NAME:-my_wallet}"
WALLET_HOTKEY="${WALLET_HOTKEY:-miner_hotkey}"
SUBTENSOR_NETWORK="${SUBTENSOR_NETWORK:-test}"
AXON_PORT="${AXON_PORT:-8091}"
MOCK="${MOCK:-0}"
EPOCH_LENGTH="${EPOCH_LENGTH:-100}"
FORCE_VALIDATOR_PERMIT="${FORCE_VALIDATOR_PERMIT:-1}"
ALLOW_NON_REGISTERED="${ALLOW_NON_REGISTERED:-0}"

EXTRA_ARGS=()
if [[ "${MOCK}" == "1" ]]; then
  EXTRA_ARGS+=(--mock)
fi
if [[ "${FORCE_VALIDATOR_PERMIT}" == "1" ]]; then
  EXTRA_ARGS+=(--blacklist.force_validator_permit)
fi
if [[ "${ALLOW_NON_REGISTERED}" == "1" ]]; then
  EXTRA_ARGS+=(--blacklist.allow_non_registered)
fi

python neurons/miner.py \
  --netuid "${NETUID}" \
  --wallet.name "${WALLET_NAME}" \
  --wallet.hotkey "${WALLET_HOTKEY}" \
  --axon.port "${AXON_PORT}" \
  --subtensor.network "${SUBTENSOR_NETWORK}" \
  --neuron.epoch_length "${EPOCH_LENGTH}" \
  "${EXTRA_ARGS[@]}"
