#!/bin/bash
# Start Maya backend in test mode with structured logs

set -e

SESSION_ID=$(date +%Y%m%d_%H%M%S)
export MAYA_TEST_SESSION="$SESSION_ID"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
export LOG_DIR="${AGENT_ROOT}/logs/sessions/$SESSION_ID"
mkdir -p "$LOG_DIR"

echo "SESSION_ID=$SESSION_ID" > /tmp/maya_test_session.env
echo "LOG_DIR=$LOG_DIR" >> /tmp/maya_test_session.env

cd "$AGENT_ROOT"

# Start backend
nohup ./venv/bin/python agent.py dev \
  > "$LOG_DIR/agent_full.log" 2>&1 &

echo "AGENT_PID=$!" >> /tmp/maya_test_session.env

# Wait for boot
echo "Waiting for backend to boot..."
for i in $(seq 1 30); do
  if grep -Eq "MAYA RUNTIME READY|worker connected|Global agent ready|Token Server started" "$LOG_DIR/agent_full.log" 2>/dev/null; then
    echo "Backend ready."
    break
  fi
  sleep 1
done

echo "LOG_DIR: $LOG_DIR"
echo "Backend started. PID: $(cat /tmp/maya_test_session.env | grep AGENT_PID)"
