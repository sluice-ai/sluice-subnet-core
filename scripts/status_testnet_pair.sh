#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="${LOG_DIR:-${ROOT_DIR}/.run_logs}"

status_role() {
  local role="$1"
  local pid_file="$2"
  local log_file="$3"

  if [[ ! -f "${pid_file}" ]]; then
    echo "${role}: stopped (no pid file)"
    return 0
  fi

  local pid
  pid="$(tr -d '[:space:]' < "${pid_file}")"
  if [[ -n "${pid}" ]] && kill -0 "${pid}" 2>/dev/null; then
    echo "${role}: running pid=${pid} log=${log_file}"
    return 0
  fi

  echo "${role}: stopped (stale pid=${pid:-none}) log=${log_file}"
}

status_role "miner" "${LOG_DIR}/miner_testnet.pid" "${LOG_DIR}/miner_testnet.log"
status_role "validator" "${LOG_DIR}/validator_testnet.pid" "${LOG_DIR}/validator_testnet.log"
