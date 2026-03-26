#!/bin/bash
#
# Log Capture Script for Maya-One Testing
#
# This script captures log output from the Maya-One agent and splits it
# into different files based on content type.
#
# Log Format Documentation:
# The Maya-One agent uses Python logging with the following format:
#   LEVEL:module.name:Message text trace_id=uuid
#
# Examples:
#   INFO:core.utils.server_patch:🔧 Applying LiveKit HttpServer patch trace_id=...
#   ERROR:providers.llmprovider:❌ Configuration error... trace_id=...
#
# Usage:
#   ./scripts/start_test_capture.sh
#
# Output: Logs captured to Agent/logs/flutter_test_run/YYYYMMDD_HHMMSS/
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
SESSION_DIR="${BASE_DIR}/logs/flutter_test_run/$(date +%Y%m%d_%H%M%S)"

mkdir -p "$SESSION_DIR"

echo "=========================================="
echo "  Maya-One Log Capture Session"
echo "  Started: $(date)"
echo "  Output: $SESSION_DIR"
echo "=========================================="
echo ""

# Store session path for other tools
echo "$SESSION_DIR" > /tmp/maya_current_session.txt

# Determine log file location
LOG_FILE="${BASE_DIR}/logs/audit.log"
if [ ! -f "$LOG_FILE" ]; then
    # Fallback to any .log file in logs directory
    LOG_FILE=$(find "${BASE_DIR}/logs" -name "*.log" -type f 2>/dev/null | head -1)
    if [ -z "$LOG_FILE" ]; then
        echo "⚠️  Warning: No log file found. Will retry when available."
        LOG_FILE="${BASE_DIR}/logs/audit.log"
    fi
fi

echo "Monitoring log file: $LOG_FILE"
echo ""

# Full log — everything
tail -f "$LOG_FILE" 2>/dev/null > "$SESSION_DIR/agent_full.log" &
FULL_PID=$!

# Routing decisions only
# Pattern: matches routing-related log lines including agent_router_decision, routing_mode, etc.
tail -f "$LOG_FILE" 2>/dev/null | grep -E \
    "agent_router_decision|routing_mode|route_completed|fast_path_matched|identity_fast_path|memory_skipped|context_builder_memory_skipped" \
    > "$SESSION_DIR/routing_only.log" &
ROUTE_PID=$!

# Tool calls only
# Pattern: matches tool execution, tool results, task lifecycle
tail -f "$LOG_FILE" 2>/dev/null | grep -E \
    "tool_call|tool_execution|tool_result|tool_invoked|run_shell_command|web_search|get_weather|get_time|open_app|task_created|task_completed|task_failed|plan_generated|send_message_accepted|chat_event_published" \
    > "$SESSION_DIR/tool_calls.log" &
TOOL_PID=$!

# Errors and warnings only
# Pattern: matches ERROR/WARNING levels and error-related keywords
tail -f "$LOG_FILE" 2>/dev/null | grep -E \
    "^(ERROR|WARNING|WARN):|exception|traceback|failed|blocked|action_blocked|validation_failed|tool_markup_leak|session_say_timeout|stt_failover|circuit_breaker" \
    > "$SESSION_DIR/errors_warnings.log" &
ERR_PID=$!

# Sentinel logs (new)
# Pattern: matches sentinel events
tail -f "$LOG_FILE" 2>/dev/null | grep -E \
    "sentinel_|sentinel_.*_detected|sentinel_.*_CRITICAL|sentinel_.*_ok" \
    > "$SESSION_DIR/sentinel.log" &
SENTINEL_PID=$!

echo "Capturing to: $SESSION_DIR"
echo "  - agent_full.log: All log output"
echo "  - routing_only.log: Routing decisions"
echo "  - tool_calls.log: Tool executions"
echo "  - errors_warnings.log: Errors and warnings"
echo "  - sentinel.log: Behavioral sentinel events"
echo ""
echo "PIDs: full=$FULL_PID route=$ROUTE_PID tool=$TOOL_PID err=$ERR_PID sentinel=$SENTINEL_PID"
echo "$FULL_PID $ROUTE_PID $TOOL_PID $ERR_PID $SENTINEL_PID" > /tmp/maya_capture_pids.txt

echo ""
echo "To stop capture:"
echo "  kill \$(cat /tmp/maya_capture_pids.txt)"
echo ""
echo "Watching routing decisions live (Ctrl+C to stop viewing, capture continues):"
echo "---"

# Show routing log live, but capture continues in background
trap 'echo ""; echo "Viewing stopped. Capture still running in background."; echo "To stop all capture: kill \$(cat /tmp/maya_capture_pids.txt)"; exit 0' INT
tail -f "$SESSION_DIR/routing_only.log" 2>/dev/null || true
