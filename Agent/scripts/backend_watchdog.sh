#!/bin/bash
# Maya backend watchdog service.
# Keeps `agent.py dev` alive and restarts it on crashes.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
AGENT_DIR="$ROOT_DIR/Agent"
RUN_DIR="$AGENT_DIR/run"
LOG_ROOT="$AGENT_DIR/logs/sessions"
SUPERVISOR_PID_FILE="$RUN_DIR/backend_supervisor.pid"
AGENT_PID_FILE="$RUN_DIR/backend_agent.pid"
ACTIVE_SESSION_FILE="$RUN_DIR/backend_active_session"
SUPERVISOR_LOG="$RUN_DIR/backend_supervisor.log"
RESTART_DELAY_S="${MAYA_RESTART_DELAY_S:-2}"

mkdir -p "$RUN_DIR" "$LOG_ROOT"

is_pid_running() {
  local pid="$1"
  [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null
}

read_pid() {
  local file="$1"
  if [[ -f "$file" ]]; then
    tr -d '[:space:]' < "$file"
  fi
}

stop_child_if_needed() {
  local child_pid
  child_pid="$(read_pid "$AGENT_PID_FILE" || true)"
  if is_pid_running "${child_pid:-}"; then
    kill "$child_pid" 2>/dev/null || true
    sleep 1
    if is_pid_running "${child_pid:-}"; then
      kill -9 "$child_pid" 2>/dev/null || true
    fi
  fi
  rm -f "$AGENT_PID_FILE"
}

run_loop() {
  cd "$AGENT_DIR"
  echo "$$" > "$SUPERVISOR_PID_FILE"
  trap 'stop_child_if_needed; rm -f "$SUPERVISOR_PID_FILE"; exit 0' INT TERM

  while true; do
    SESSION_ID="$(date +%Y%m%d_%H%M%S)"
    LOG_DIR="$LOG_ROOT/$SESSION_ID"
    mkdir -p "$LOG_DIR"
    echo "$SESSION_ID" > "$ACTIVE_SESSION_FILE"

    echo "[$(date -Is)] backend_start session=$SESSION_ID" >> "$SUPERVISOR_LOG"
    stdbuf -oL -eL ./venv/bin/python agent.py dev > "$LOG_DIR/agent_full.log" 2>&1 &
    CHILD_PID=$!
    echo "$CHILD_PID" > "$AGENT_PID_FILE"
    echo "$CHILD_PID" > "$LOG_DIR/agent.pid"

    set +e
    wait "$CHILD_PID"
    EXIT_CODE=$?
    set -e
    rm -f "$AGENT_PID_FILE"
    echo "[$(date -Is)] backend_exit session=$SESSION_ID pid=$CHILD_PID code=$EXIT_CODE" >> "$SUPERVISOR_LOG"

    sleep "$RESTART_DELAY_S"
  done
}

start_supervisor() {
  local existing_pid
  existing_pid="$(read_pid "$SUPERVISOR_PID_FILE" || true)"
  if is_pid_running "${existing_pid:-}"; then
    echo "Backend watchdog already running (PID $existing_pid)."
    exit 0
  fi

  nohup "$0" run >> "$SUPERVISOR_LOG" 2>&1 &
  local new_pid=$!
  sleep 1
  if is_pid_running "$new_pid"; then
    echo "Backend watchdog started (PID $new_pid)."
    echo "Supervisor log: $SUPERVISOR_LOG"
  else
    echo "Failed to start backend watchdog."
    exit 1
  fi
}

stop_supervisor() {
  local sup_pid child_pid
  sup_pid="$(read_pid "$SUPERVISOR_PID_FILE" || true)"
  child_pid="$(read_pid "$AGENT_PID_FILE" || true)"

  if is_pid_running "${sup_pid:-}"; then
    kill "$sup_pid" 2>/dev/null || true
    sleep 1
    if is_pid_running "${sup_pid:-}"; then
      kill -9 "$sup_pid" 2>/dev/null || true
    fi
  fi

  if is_pid_running "${child_pid:-}"; then
    kill "$child_pid" 2>/dev/null || true
    sleep 1
    if is_pid_running "${child_pid:-}"; then
      kill -9 "$child_pid" 2>/dev/null || true
    fi
  fi

  rm -f "$SUPERVISOR_PID_FILE" "$AGENT_PID_FILE"
  echo "Backend watchdog stopped."
}

status_supervisor() {
  local sup_pid child_pid session_id
  sup_pid="$(read_pid "$SUPERVISOR_PID_FILE" || true)"
  child_pid="$(read_pid "$AGENT_PID_FILE" || true)"
  session_id="$(read_pid "$ACTIVE_SESSION_FILE" || true)"

  if is_pid_running "${sup_pid:-}"; then
    echo "watchdog: running (PID $sup_pid)"
  else
    echo "watchdog: stopped"
  fi

  if is_pid_running "${child_pid:-}"; then
    echo "agent: running (PID $child_pid)"
  else
    echo "agent: stopped"
  fi

  if [[ -n "${session_id:-}" ]]; then
    echo "session: $session_id"
    echo "log: $LOG_ROOT/$session_id/agent_full.log"
  fi

  if curl -fsS --max-time 2 http://127.0.0.1:5050/health >/dev/null 2>&1; then
    echo "health: ok (http://127.0.0.1:5050/health)"
  else
    echo "health: unavailable"
  fi
}

follow_logs() {
  local session_id
  session_id="$(read_pid "$ACTIVE_SESSION_FILE" || true)"
  if [[ -z "${session_id:-}" ]]; then
    echo "No active session log found."
    exit 1
  fi
  tail -f "$LOG_ROOT/$session_id/agent_full.log"
}

case "${1:-}" in
  run)
    run_loop
    ;;
  start)
    start_supervisor
    ;;
  stop)
    stop_supervisor
    ;;
  restart)
    stop_supervisor
    start_supervisor
    ;;
  status)
    status_supervisor
    ;;
  logs)
    follow_logs
    ;;
  *)
    echo "Usage: $0 {start|stop|restart|status|logs|run}"
    exit 1
    ;;
esac
