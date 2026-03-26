#!/bin/bash
# Run full Maya integration test suite
# This script: starts backend → waits → runs Dart tests → reports

set -e

echo "=== Maya-One Integration Test Runner ==="
echo "Date: $(date)"
echo ""

# Step 1: Start backend
echo "--- Starting backend ---"
./Agent/scripts/start_test_backend.sh &
BACKEND_SCRIPT_PID=$!

# Wait for token server
echo "Waiting for token server..."
for i in $(seq 1 30); do
  if curl -s http://localhost:5050/token > /dev/null 2>&1; then
    echo "Token server up."
    break
  fi
  sleep 2
done

# Step 2: Run Dart integration tests
echo ""
echo "--- Running Dart integration tests ---"
cd agent-starter-flutter-main

flutter test \
  test/integration/maya_full_integration_test.dart \
  --timeout=120s \
  --reporter=expanded \
  2>&1 | tee /tmp/maya_integration_results.log

FLUTTER_EXIT=${PIPESTATUS[0]}

# Step 3: Generate report
echo ""
echo "=== INTEGRATION TEST REPORT ==="
echo "Date: $(date)"
echo ""

PASS_COUNT=$(grep -c "✅ PASS" /tmp/maya_integration_results.log || true)
FAIL_COUNT=$(grep -c "❌ FAIL" /tmp/maya_integration_results.log || true)
TOTAL=$((PASS_COUNT + FAIL_COUNT))

echo "Total:  $TOTAL"
echo "Passed: $PASS_COUNT"
echo "Failed: $FAIL_COUNT"
echo ""

if [ "$FAIL_COUNT" -gt 0 ]; then
  echo "FAILED TESTS:"
  grep "❌ FAIL" /tmp/maya_integration_results.log
fi

# Step 4: Also run pytest to confirm no backend regressions
echo ""
echo "--- Backend pytest gate ---"
cd ../Agent
./venv/bin/pytest tests/ -q --tb=no 2>&1 | tail -3

# Step 5: Kill backend
kill $BACKEND_SCRIPT_PID 2>/dev/null || true
SOURCE_PID=$(cat /tmp/maya_test_session.env | grep AGENT_PID | cut -d= -f2)
kill $SOURCE_PID 2>/dev/null || true

echo ""
echo "=== DONE ==="
exit $FLUTTER_EXIT
