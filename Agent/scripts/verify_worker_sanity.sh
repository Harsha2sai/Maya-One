#!/bin/bash

# PREFLIGHT: Worker Sanity Check
# Runs local simulation with InMemoryTaskStore to verify Worker-LLM integration loop.

# Ensure we are in Agent dir
cd "$(dirname "$0")/.."
PREFLIGHT_DIR="preflight_artifacts"
mkdir -p "$PREFLIGHT_DIR"

# Use venv python if available
if [ -f "venv/bin/python3" ]; then
    PYTHON_CMD="venv/bin/python3"
else
    PYTHON_CMD="python3"
fi

export PYTHONPATH=$PYTHONPATH:$(pwd)

echo "Running Local Worker Simulation (In-Memory)..."
$PYTHON_CMD scripts/verify_worker_local_simulation.py > "$PREFLIGHT_DIR/worker_sanity.log" 2>&1
EXIT_CODE=$?

if [ $EXIT_CODE -ne 0 ]; then
    echo "❌ Worker Sanity Check FAILED"
    echo "---- Log Tail ----"
    tail -n 20 "$PREFLIGHT_DIR/worker_sanity.log"
    echo "WORKER_SANITY_FAIL" > "$PREFLIGHT_DIR/status.txt"
    exit 1
else
    echo "✅ Worker Sanity Check PASSED"
    grep "Result" "$PREFLIGHT_DIR/worker_sanity.log"
    echo "WORKER_SANITY_OK" > "$PREFLIGHT_DIR/status.txt"
    exit 0
fi
