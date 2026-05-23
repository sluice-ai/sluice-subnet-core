#!/usr/bin/env bash
set -euo pipefail

export BT_NO_PARSE_CLI_ARGS=false

source venv/bin/activate

NETUID="${NETUID:-476}"
WALLET_NAME="${WALLET_NAME:-my_wallet}"
WALLET_HOTKEY="${WALLET_HOTKEY:-validator_hotkey}"
SUBTENSOR_NETWORK="${SUBTENSOR_NETWORK:-test}"
AXON_PORT="${AXON_PORT:-8092}"
MOCK="${MOCK:-0}"
AXON_OFF="${AXON_OFF:-0}"
TIMEOUT="${TIMEOUT:-10}"
SAMPLE_SIZE="${SAMPLE_SIZE:-50}"
NUM_CONCURRENT_FORWARDS="${NUM_CONCURRENT_FORWARDS:-1}"
CHALLENGE_INTERVAL="${CHALLENGE_INTERVAL:-12}"
EPOCH_LENGTH="${EPOCH_LENGTH:-100}"
DISABLE_SET_WEIGHTS="${DISABLE_SET_WEIGHTS:-0}"
VPERMIT_TAO_LIMIT="${VPERMIT_TAO_LIMIT:-4096}"

EXTRA_ARGS=()
if [[ "${MOCK}" == "1" ]]; then
  EXTRA_ARGS+=(--mock)
fi
if [[ "${AXON_OFF}" == "1" ]]; then
  EXTRA_ARGS+=(--neuron.axon_off)
fi
if [[ "${DISABLE_SET_WEIGHTS}" == "1" ]]; then
  EXTRA_ARGS+=(--neuron.disable_set_weights)
fi

python neurons/validator.py \
  --netuid "${NETUID}" \
  --wallet.name "${WALLET_NAME}" \
  --wallet.hotkey "${WALLET_HOTKEY}" \
  --axon.port "${AXON_PORT}" \
  --subtensor.network "${SUBTENSOR_NETWORK}" \
  --neuron.timeout "${TIMEOUT}" \
  --neuron.sample_size "${SAMPLE_SIZE}" \
  --neuron.num_concurrent_forwards "${NUM_CONCURRENT_FORWARDS}" \
  --neuron.challenge_interval "${CHALLENGE_INTERVAL}" \
  --neuron.epoch_length "${EPOCH_LENGTH}" \
  --neuron.vpermit_tao_limit "${VPERMIT_TAO_LIMIT}" \
  "${EXTRA_ARGS[@]}"
