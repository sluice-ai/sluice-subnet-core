#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="${LOG_DIR:-${ROOT_DIR}/.run_logs}"
MINER_ENV_FILE="${MINER_ENV_FILE:-${ROOT_DIR}/.env.miner}"
VALIDATOR_ENV_FILE="${VALIDATOR_ENV_FILE:-${ROOT_DIR}/.env.validator}"
MINER_PID_FILE="${MINER_PID_FILE:-${LOG_DIR}/miner_testnet.pid}"
VALIDATOR_PID_FILE="${VALIDATOR_PID_FILE:-${LOG_DIR}/validator_testnet.pid}"
MINER_LOG_FILE="${MINER_LOG_FILE:-${LOG_DIR}/miner_testnet.log}"
VALIDATOR_LOG_FILE="${VALIDATOR_LOG_FILE:-${LOG_DIR}/validator_testnet.log}"
STARTUP_DELAY="${STARTUP_DELAY:-20}"

mkdir -p "${LOG_DIR}"

is_running() {
  local pid_file="$1"
  [[ -f "${pid_file}" ]] || return 1
  local pid
  pid="$(tr -d '[:space:]' < "${pid_file}")"
  [[ -n "${pid}" ]] && kill -0 "${pid}" 2>/dev/null
}

start_role() {
  local role="$1"
  local env_file="$2"
  local pid_file="$3"
  local log_file="$4"
  local command="$5"

  if is_running "${pid_file}"; then
    echo "${role} already running with pid $(tr -d '[:space:]' < "${pid_file}")"
    return 0
  fi

  rm -f "${pid_file}"
  touch "${log_file}"
  (
    cd "${ROOT_DIR}"
    if command -v setsid >/dev/null 2>&1; then
      ENV_FILE="${env_file}" nohup setsid "${command}" >> "${log_file}" 2>&1 < /dev/null &
    else
      ENV_FILE="${env_file}" nohup "${command}" >> "${log_file}" 2>&1 < /dev/null &
    fi
    echo "$!" > "${pid_file}"
  )

  sleep 1
  if ! is_running "${pid_file}"; then
    echo "${role} failed to stay running. Last log lines:"
    tail -n 40 "${log_file}" || true
    return 1
  fi

  echo "${role} started with pid $(tr -d '[:space:]' < "${pid_file}")"
  echo "${role} log: ${log_file}"
}

start_role "miner" "${MINER_ENV_FILE}" "${MINER_PID_FILE}" "${MINER_LOG_FILE}" "${ROOT_DIR}/start_miner.sh"
sleep "${STARTUP_DELAY}"
start_role "validator" "${VALIDATOR_ENV_FILE}" "${VALIDATOR_PID_FILE}" "${VALIDATOR_LOG_FILE}" "${ROOT_DIR}/start_validator.sh"

echo "pair started"
