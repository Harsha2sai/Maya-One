#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
LOG_DIR="${AGENT_DIR}/logs/manual_test/${TIMESTAMP}"
FULL_LOG="${LOG_DIR}/agent_full.log"
ROUTING_LOG="${LOG_DIR}/routing_only.log"

mkdir -p "${LOG_DIR}"
touch "${FULL_LOG}" "${ROUTING_LOG}"

echo "Manual test log directory: ${LOG_DIR}"

kill_5050_listener() {
  local pids=""

  if command -v lsof >/dev/null 2>&1; then
    pids="$(lsof -ti tcp:5050 -sTCP:LISTEN 2>/dev/null || true)"
  elif command -v fuser >/dev/null 2>&1; then
    pids="$(fuser 5050/tcp 2>/dev/null || true)"
  fi

  if [[ -n "${pids}" ]]; then
    echo "Stopping existing process(es) on port 5050: ${pids}"
    kill ${pids} 2>/dev/null || true
    sleep 1
    for pid in ${pids}; do
      if kill -0 "${pid}" 2>/dev/null; then
        kill -9 "${pid}" 2>/dev/null || true
      fi
    done
  fi
}

kill_5050_listener

(
  tail -n 0 -F "${FULL_LOG}" 2>/dev/null \
    | grep -E --line-buffered "agent_router_decision|route_completed|fast_path|tts_|memory_|tool_call|ERROR|WARNING" \
    >> "${ROUTING_LOG}"
) &
ROUTING_PID=$!

cleanup_done=0
AGENT_PID=0

cleanup() {
  if [[ "${cleanup_done}" -eq 1 ]]; then
    return
  fi
  cleanup_done=1

  if [[ "${AGENT_PID}" -gt 0 ]] && kill -0 "${AGENT_PID}" 2>/dev/null; then
    kill "${AGENT_PID}" 2>/dev/null || true
    wait "${AGENT_PID}" 2>/dev/null || true
  fi

  if kill -0 "${ROUTING_PID}" 2>/dev/null; then
    kill "${ROUTING_PID}" 2>/dev/null || true
    wait "${ROUTING_PID}" 2>/dev/null || true
  fi

  echo "Session log saved to: ${FULL_LOG}"
  echo "Routing summary: ${ROUTING_LOG}"
}

trap 'cleanup; exit 0' INT TERM

cd "${AGENT_DIR}"
PYTHON_BIN="./venv/bin/python"
if [[ ! -x "${PYTHON_BIN}" ]]; then
  if command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="python3"
  else
    PYTHON_BIN="python"
  fi
fi

echo "Starting agent: ${PYTHON_BIN} agent.py dev"
echo "Streaming logs to terminal and ${FULL_LOG}"

stdbuf -oL -eL "${PYTHON_BIN}" agent.py dev > >(tee -a "${FULL_LOG}") 2>&1 &
AGENT_PID=$!

wait "${AGENT_PID}" || true
cleanup
