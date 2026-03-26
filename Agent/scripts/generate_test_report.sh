#!/bin/bash
set -e

SESSION_DIR=$(cat /tmp/maya_current_session.txt 2>/dev/null)
if [ -z "$SESSION_DIR" ]; then
  echo "ERROR: No active session found. Run start_test_capture.sh first."
  exit 1
fi

REPORT="$SESSION_DIR/test_report.md"

echo "# Maya-One Flutter Test Run Report" > "$REPORT"
echo "Generated: $(date)" >> "$REPORT"
echo "Session: $SESSION_DIR" >> "$REPORT"
echo "" >> "$REPORT"

echo "## Routing Decision Summary" >> "$REPORT"
echo '```' >> "$REPORT"
grep "agent_router_decision" "$SESSION_DIR/routing_only.log" \
  | sed 's/.*agent_router_decision/agent_router_decision/' \
  | sort | uniq -c | sort -rn >> "$REPORT"
echo '```' >> "$REPORT"

echo "" >> "$REPORT"
echo "## Fast-Path Hits" >> "$REPORT"
echo '```' >> "$REPORT"
grep -c "fast_path_matched" "$SESSION_DIR/routing_only.log" \
  | xargs -I{} echo "fast_path_matched: {} hits" >> "$REPORT" 2>/dev/null || \
  echo "fast_path_matched: 0 hits" >> "$REPORT"
echo '```' >> "$REPORT"

echo "" >> "$REPORT"
echo "## Tool Calls Made" >> "$REPORT"
echo '```' >> "$REPORT"
grep "tool_call\|tool_invoked" "$SESSION_DIR/tool_calls.log" \
  | sed 's/.*tool_call/tool_call/' \
  | sort | uniq -c | sort -rn >> "$REPORT"
echo '```' >> "$REPORT"

echo "" >> "$REPORT"
echo "## Errors and Warnings" >> "$REPORT"
echo '```' >> "$REPORT"
cat "$SESSION_DIR/errors_warnings.log" >> "$REPORT"
echo '```' >> "$REPORT"

echo "" >> "$REPORT"
echo "## Route Completed Events" >> "$REPORT"
echo '```' >> "$REPORT"
grep "route_completed\|action_attempted" "$SESSION_DIR/routing_only.log" \
  >> "$REPORT" 2>/dev/null || echo "none" >> "$REPORT"
echo '```' >> "$REPORT"

echo "Report written to: $REPORT"
cat "$REPORT"

chmod +x Agent/scripts/generate_test_report.sh
