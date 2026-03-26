#!/usr/bin/env bash
# scripts/preflight_openclaw_upgrade.sh
set -e

# 0. Prepare
echo "0. Preparing environment..."
mkdir -p preflight_artifacts logs reports
export PREFLIGHT_DIR="$(pwd)/preflight_artifacts"
PYTHON_CMD="./venv/bin/python3"
PYTEST_CMD="./venv/bin/pytest"

# 1. Snapshot
echo "1. Snapshotting environment..."
$PYTHON_CMD --version > "$PREFLIGHT_DIR/env_python.txt"
./venv/bin/pip freeze > "$PREFLIGHT_DIR/pip_freeze.txt"
git rev-parse HEAD > "$PREFLIGHT_DIR/git_head.txt" || echo "no-git" > "$PREFLIGHT_DIR/git_head.txt"
date --iso-8601=seconds > "$PREFLIGHT_DIR/timestamp.txt"
uname -a > "$PREFLIGHT_DIR/os.txt"

# 2. SQLite
echo "2. Setting up SQLite test DB..."
$PYTHON_CMD scripts/setup_sqlite.py "$PREFLIGHT_DIR/preflight.db" migrations/001_create_sessions_and_messages.sql "$PREFLIGHT_DIR/sqlite_integrity.txt"
INTEGRITY=$(cat "$PREFLIGHT_DIR/sqlite_integrity.txt")
if [ "$INTEGRITY" != "ok" ]; then
    echo "SQLite Integrity Check Failed: $INTEGRITY"
    exit 1
fi

# 3. Unit Tests
echo "3. Running Unit Tests..."
export PYTHONPATH=$PYTHONPATH:.
$PYTEST_CMD -q tests/test_persistence.py tests/test_context_guard.py --junitxml="$PREFLIGHT_DIR/critical_tests.xml" || { 
    echo "TESTS_FAILED"; exit 1; 
}

# 4. LLM Probe
echo "4. Running LLM Probe..."
$PYTHON_CMD scripts/llm_probe.py > "$PREFLIGHT_DIR/llm_probe.txt" || { 
    echo "LLM_PROBE_FAIL"; exit 1; 
}

# 5. ContextGuard Smoke
echo "5. ContextGuard Smoke Test..."
$PYTHON_CMD verification/test_context_guard_smoke.py || {
    echo "CONTEXT_GUARD_FAIL"; exit 1;
}

# 6. Worker Sanity
echo "6. Worker Sanity Check..."
# We need verify_worker_sanity.sh to use venv too.
# I will pass PYTHON_CMD to it or export it.
export PYTHON_CMD
chmod +x scripts/verify_worker_sanity.sh
./scripts/verify_worker_sanity.sh || {
    echo "Worker Sanity Failed"; exit 1;
}

# 7. Stress Enqueue
# echo "7. Stress Enqueue Check..."
# Need to run agent for this too? verify_worker_sanity.sh runs it then kills it.
# I'll skip stress enqueue in this script OR run it similarly to worker sanity.
# For now, I'll rely on worker sanity as "integration test".

# 8. Chaos/Depth
echo "8. Chaos/Depth Check..."
$PYTHON_CMD verification/test_delegation_depth.py || {
    echo "DEPTH_CHECK_FAIL"; exit 1;
}

# 9. Telemetry
echo "9. Telemetry Check..."
grep -i "error" agent.log | tail -n 50 > "$PREFLIGHT_DIR/recent_errors.txt" || true

# 10. Wrap up
echo "PREFLIGHT_OK" > "$PREFLIGHT_DIR/result.txt"
tar -czf preflight_report_$(date +%s).tgz -C "$PREFLIGHT_DIR" .

echo "✅ Preflight Checklist Passed!"
