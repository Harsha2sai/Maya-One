#!/bin/bash
# Maya-One diagnostic startup with session logs

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
AGENT_DIR="$ROOT_DIR/Agent"
mkdir -p "$AGENT_DIR/logs/sessions"

SESSION_ID="$(date +%Y%m%d_%H%M%S)"
LOG_DIR="$AGENT_DIR/logs/sessions/$SESSION_ID"
mkdir -p "$LOG_DIR"

echo "=== Maya-One Diagnostic Session: $SESSION_ID ==="
echo "Logs: $LOG_DIR"

cd "$AGENT_DIR"

./venv/bin/python agent.py dev 2>&1 | tee "$LOG_DIR/agent_full.log" &
AGENT_PID=$!
echo "$AGENT_PID" > "$LOG_DIR/agent.pid"
echo "Agent PID: $AGENT_PID"

sleep 5

tail -f "$LOG_DIR/agent_full.log" | grep -E \
  "agent_router_decision|fast_path|tool_call|route_completed|action_blocked|memory|task_|dropped_utterance|media_route|research_route|system_action|voice_summary|display_text|tts_|tts_fallback_|tts_silent_drop|spotify_api_request|worker_memory_telemetry|stt_|ERROR|WARNING|Exception|Traceback" \
  > "$LOG_DIR/filtered.log" &
FILTER_PID=$!
echo "$FILTER_PID" > "$LOG_DIR/filter.pid"
echo "Filter PID: $FILTER_PID"

echo
echo "Watch filtered logs: tail -f $LOG_DIR/filtered.log"
echo "Watch full logs:     tail -f $LOG_DIR/agent_full.log"
echo "Stop:                kill $AGENT_PID $FILTER_PID"

wait "$AGENT_PID"
