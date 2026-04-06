#!/usr/bin/env bash
# =============================================================================
# run_phase27_voice_certification.sh
#
# Phase 27 Voice Certification Wrapper
#
# Starts the backend agent (dev mode), waits for readiness, runs the
# multi-probe certification suite, captures verdict, stops backend cleanly.
#
# Exit codes:
#   0 — All probes passed
#   1 — One or more probes failed
#   2 — Setup failure (backend didn't start, LiveKit unreachable, etc.)
#
# Usage:
#   cd /home/harsha/Downloads/Projects/v2/Maya-One-phase-0-2/Agent
#   bash scripts/run_phase27_voice_certification.sh
#
#   Optional env overrides:
#     CERT_TIMEOUT=90               # per-run timeout (seconds)
#     CERT_ROOM_PREFIX=maya-cert    # LiveKit room prefix
#     CERT_JSON_OUTPUT=/tmp/p27.json
#     BACKEND_STARTUP_WAIT=12       # seconds to wait for backend to be ready
#     SKIP_BACKEND_START=1          # set to skip starting backend (use existing)
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENT_DIR="$(dirname "$SCRIPT_DIR")"
VENV="$AGENT_DIR/venv/bin"

CERT_TIMEOUT="${CERT_TIMEOUT:-90}"
CERT_ROOM_PREFIX="${CERT_ROOM_PREFIX:-maya-cert}"
CERT_JSON_OUTPUT="${CERT_JSON_OUTPUT:-/tmp/maya_phase27_cert.json}"
BACKEND_STARTUP_WAIT="${BACKEND_STARTUP_WAIT:-12}"
SKIP_BACKEND_START="${SKIP_BACKEND_START:-0}"
BACKEND_LOG="/tmp/maya_phase27_backend.log"
BACKEND_PID_FILE="/tmp/maya_phase27_backend.pid"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log()   { echo -e "[$(date +%H:%M:%S)] $*"; }
ok()    { echo -e "${GREEN}[PASS]${NC} $*"; }
fail()  { echo -e "${RED}[FAIL]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }

# ---------------------------------------------------------------------------
# Cleanup handler
# ---------------------------------------------------------------------------
BACKEND_PID=""

cleanup() {
    if [[ -n "$BACKEND_PID" ]] && kill -0 "$BACKEND_PID" 2>/dev/null; then
        log "Stopping backend (PID $BACKEND_PID)..."
        kill "$BACKEND_PID" 2>/dev/null || true
        wait "$BACKEND_PID" 2>/dev/null || true
        log "Backend stopped."
    fi
    rm -f "$BACKEND_PID_FILE"
}

trap cleanup EXIT INT TERM

# ---------------------------------------------------------------------------
# Step 0 — Sanity checks
# ---------------------------------------------------------------------------
log "=== Phase 27 Voice Certification ==="
log "Agent dir: $AGENT_DIR"
log "Timeout: ${CERT_TIMEOUT}s"

cd "$AGENT_DIR"

if [[ ! -f "$VENV/python" ]]; then
    fail "Virtualenv not found at $VENV — run: python -m venv venv && pip install -r requirements.txt"
    exit 2
fi

if [[ ! -f "agent.py" ]]; then
    fail "agent.py not found — are you in the Agent directory?"
    exit 2
fi

if [[ ! -f "scripts/verify_livekit_voice_roundtrip.py" ]]; then
    fail "scripts/verify_livekit_voice_roundtrip.py not found"
    exit 2
fi

# ---------------------------------------------------------------------------
# Step 1 — Start backend (unless skipped)
# ---------------------------------------------------------------------------
if [[ "$SKIP_BACKEND_START" == "1" ]]; then
    warn "SKIP_BACKEND_START=1 — assuming backend is already running"
else
    log "Starting backend in dev mode..."
    "$VENV/python" agent.py dev \
        >"$BACKEND_LOG" 2>&1 &
    BACKEND_PID=$!
    echo "$BACKEND_PID" > "$BACKEND_PID_FILE"
    log "Backend PID: $BACKEND_PID  log: $BACKEND_LOG"

    # Wait for readiness signal
    log "Waiting ${BACKEND_STARTUP_WAIT}s for backend to be ready..."
    sleep "$BACKEND_STARTUP_WAIT"

    if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
        fail "Backend process died during startup. Last 20 lines of log:"
        tail -20 "$BACKEND_LOG" || true
        exit 2
    fi

    # Check /health endpoint if backend exposes HTTP
    HEALTH_URL="${BACKEND_HEALTH_URL:-http://localhost:8000/health}"
    if command -v curl &>/dev/null; then
        for i in 1 2 3; do
            if curl -sf "$HEALTH_URL" >/dev/null 2>&1; then
                ok "Backend /health OK"
                break
            fi
            if [[ $i -eq 3 ]]; then
                warn "/health check failed (non-fatal — LiveKit probe will confirm liveness)"
            fi
            sleep 2
        done
    else
        warn "curl not available — skipping /health check"
    fi
fi

# ---------------------------------------------------------------------------
# Step 2 — Run certification suite
# ---------------------------------------------------------------------------
log "Running Phase 27 certification probes..."
log "Room prefix: $CERT_ROOM_PREFIX"
log "JSON output: $CERT_JSON_OUTPUT"

CERT_EXIT=0
"$VENV/python" scripts/verify_livekit_voice_roundtrip.py \
    --timeout "$CERT_TIMEOUT" \
    --room-prefix "$CERT_ROOM_PREFIX" \
    --json-output "$CERT_JSON_OUTPUT" \
    || CERT_EXIT=$?

# ---------------------------------------------------------------------------
# Step 3 — Report
# ---------------------------------------------------------------------------
echo ""
log "=== Certification Result ==="

if [[ $CERT_EXIT -eq 0 ]]; then
    ok "ALL PROBES PASSED — safe to tag v0.27.0"
elif [[ $CERT_EXIT -eq 1 ]]; then
    fail "ONE OR MORE PROBES FAILED — do NOT tag v0.27.0"
    if [[ -f "$CERT_JSON_OUTPUT" ]]; then
        log "Failed probes:"
        CERT_JSON_PATH="$CERT_JSON_OUTPUT" "$VENV/python" - <<'EOF'
import json
import os

path = os.environ.get("CERT_JSON_PATH", "")
if not path:
    raise SystemExit(0)

with open(path, "r", encoding="utf-8") as fh:
    data = json.load(fh)

for p in data.get("probes", []):
    if not p.get("passed"):
        print(f"  FAIL  {p.get('name', 'unknown')}: {p.get('reason', '')}")
        if p.get("forbidden_hit"):
            print(f"        forbidden_hit: {p['forbidden_hit']}")
EOF
    fi
elif [[ $CERT_EXIT -eq 2 ]]; then
    fail "SETUP FAILURE — check backend logs: $BACKEND_LOG"
fi

# Print backend last 10 lines if backend was started by us
if [[ "$SKIP_BACKEND_START" != "1" ]] && [[ -f "$BACKEND_LOG" ]]; then
    log "Backend last 10 lines:"
    tail -10 "$BACKEND_LOG" | sed 's/^/  /'
fi

exit $CERT_EXIT
