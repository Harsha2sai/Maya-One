#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

if [ ! -x "./scripts/backend_watchdog.sh" ]; then
    chmod +x "./scripts/backend_watchdog.sh"
fi

echo "🚀 Starting Maya backend watchdog..."
./scripts/backend_watchdog.sh start
./scripts/backend_watchdog.sh status
