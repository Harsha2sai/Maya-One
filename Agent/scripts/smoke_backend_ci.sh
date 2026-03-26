#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

LOG_DIR="${ROOT_DIR}/logs/smoke_ci/$(date +%Y%m%d_%H%M%S)"
mkdir -p "${LOG_DIR}"

run_case() {
  local name="$1"
  local prompt="$2"
  local expected_regex="$3"
  local forbidden_regex="${4:-}"
  local log_file="${LOG_DIR}/${name}.log"

  echo "==> ${name}"
  timeout 25 ./venv/bin/python agent.py console <<< "${prompt}" > "${log_file}" 2>&1 || {
    echo "FAIL: ${name} timed out or crashed"
    tail -n 40 "${log_file}" || true
    exit 1
  }

  if ! grep -Eiq "${expected_regex}" "${log_file}"; then
    echo "FAIL: ${name} missing expected route token"
    echo "Expected regex: ${expected_regex}"
    tail -n 60 "${log_file}" || true
    exit 1
  fi

  if [[ -n "${forbidden_regex}" ]] && grep -Eiq "${forbidden_regex}" "${log_file}"; then
    echo "FAIL: ${name} matched forbidden token"
    echo "Forbidden regex: ${forbidden_regex}"
    tail -n 60 "${log_file}" || true
    exit 1
  fi

  echo "PASS: ${name}"
}

echo "Backend smoke logs: ${LOG_DIR}"

run_case \
  "identity_name" \
  "what is your name" \
  "agent_router_decision: 'what is your name' -> identity"

run_case \
  "memory_first_person" \
  "my name is TestUser" \
  "agent_router_decision: 'my name is testuser' -> chat" \
  "context_builder_memory_skipped"

run_case \
  "fastpath_time" \
  "what time is it" \
  "routing_mode=deterministic_fast_path" \
  "agent_router_decision"

run_case \
  "media_route" \
  "play music" \
  "agent_router_decision: 'play music' -> media_play"

run_case \
  "research_route" \
  "who invented python" \
  "agent_router_decision: 'who invented python' -> research"

echo "All backend smoke checks passed."
exit 0
