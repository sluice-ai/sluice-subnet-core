#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="${LOG_DIR:-${ROOT_DIR}/.run_logs}"

stop_role() {
  local role="$1"
  local pid_file="$2"

  if [[ ! -f "${pid_file}" ]]; then
    echo "${role} already stopped"
    return 0
  fi

  local pid
  pid="$(tr -d '[:space:]' < "${pid_file}")"
  if [[ -z "${pid}" ]] || ! kill -0 "${pid}" 2>/dev/null; then
    rm -f "${pid_file}"
    echo "${role} stale pid cleared"
    return 0
  fi

  kill "${pid}" 2>/dev/null || true
  for _ in $(seq 1 15); do
    if ! kill -0 "${pid}" 2>/dev/null; then
      rm -f "${pid_file}"
      echo "${role} stopped"
      return 0
    fi
    sleep 1
  done

  kill -TERM "${pid}" 2>/dev/null || true
  sleep 2
  if kill -0 "${pid}" 2>/dev/null; then
    echo "${role} still running after TERM: pid=${pid}"
    return 1
  fi
  rm -f "${pid_file}"
  echo "${role} stopped"
}

stop_role "validator" "${LOG_DIR}/validator_testnet.pid"
stop_role "miner" "${LOG_DIR}/miner_testnet.pid"
