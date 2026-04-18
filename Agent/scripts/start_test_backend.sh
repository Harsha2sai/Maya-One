#!/bin/bash
# Start Maya backend in test mode with structured logs

set -e

SESSION_ID=$(date +%Y%m%d_%H%M%S)
export MAYA_TEST_SESSION="$SESSION_ID"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
export LOG_DIR="${AGENT_ROOT}/logs/sessions/$SESSION_ID"
mkdir -p "$LOG_DIR"
AGENT_PID=""
READY_TIMEOUT_S="${MAYA_TEST_READY_TIMEOUT_S:-180}"

echo "SESSION_ID=$SESSION_ID" > /tmp/maya_test_session.env
echo "LOG_DIR=$LOG_DIR" >> /tmp/maya_test_session.env

cd "$AGENT_ROOT"

# Start backend
nohup ./venv/bin/python agent.py dev \
  > "$LOG_DIR/agent_full.log" 2>&1 &
AGENT_PID=$!

echo "AGENT_PID=${AGENT_PID}" >> /tmp/maya_test_session.env

# Wait for boot
echo "Waiting for backend to boot..."
ready=0
for i in $(seq 1 "${READY_TIMEOUT_S}"); do
  if grep -Eq "MAYA RUNTIME READY|worker connected|Global agent ready|Token Server started" "$LOG_DIR/agent_full.log" 2>/dev/null; then
    echo "Backend ready."
    ready=1
    break
  fi
  if ! kill -0 "${AGENT_PID}" 2>/dev/null; then
    echo "Backend process exited before readiness (pid=${AGENT_PID})."
    tail -n 80 "$LOG_DIR/agent_full.log" || true
    exit 1
  fi
  sleep 1
done

if [[ "${ready}" -ne 1 ]]; then
  echo "Backend did not reach readiness in ${READY_TIMEOUT_S}s (pid=${AGENT_PID})."
  tail -n 120 "$LOG_DIR/agent_full.log" || true
  exit 1
fi

echo "LOG_DIR: $LOG_DIR"
echo "Backend started. PID: ${AGENT_PID}"
