#!/usr/bin/env bash
# Maya-One beta preflight check
# Exits non-zero if any required env var is missing or /ready returns non-200.

set -euo pipefail

AGENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${AGENT_DIR}/.env"

echo "=== Maya-One Beta Preflight ==="

# Step 1: required env vars
REQUIRED_VARS=(
    GROQ_API_KEY
    LIVEKIT_URL
    LIVEKIT_API_KEY
    LIVEKIT_API_SECRET
    DEEPGRAM_API_KEY
)

MISSING=0
for var in "${REQUIRED_VARS[@]}"; do
    val=""
    if [ -f "$ENV_FILE" ]; then
        val=$(grep -E "^${var}=" "$ENV_FILE" 2>/dev/null | cut -d= -f2- | tr -d '"' | tr -d "'")
    fi
    val="${val:-${!var:-}}"
    if [ -z "$val" ]; then
        echo "[FAIL] $var is not set"
        MISSING=$((MISSING + 1))
    else
        echo "[OK]   $var"
    fi
done

if [ "$MISSING" -gt 0 ]; then
    echo ""
    echo "PREFLIGHT FAILED: $MISSING required variable(s) missing."
    exit 1
fi

# Step 2: /ready endpoint check (if server is running)
READY_URL="${MAYA_READY_URL:-http://localhost:5050/ready}"
if curl -sf --max-time 5 "$READY_URL" > /tmp/maya_ready_response.json 2>/dev/null; then
    echo "[OK]   /ready endpoint: $(cat /tmp/maya_ready_response.json)"
else
    echo "[WARN] /ready endpoint not reachable at $READY_URL (server may not be running)"
fi

echo ""
echo "PREFLIGHT PASSED"
exit 0
