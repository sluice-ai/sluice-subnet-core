#!/bin/sh
set -eu

echo "[entrypoint] Sluice sandbox starting" >&2
echo "[entrypoint] AGENT_RELATIVE_PATH=${AGENT_RELATIVE_PATH:-agent.py}" >&2

exec python /app/runner.py
