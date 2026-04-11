#!/usr/bin/env bash
set -euo pipefail

required_vars=(
  "GROQ_API_KEY"
  "LIVEKIT_URL"
  "LIVEKIT_API_KEY"
  "LIVEKIT_API_SECRET"
)

missing=()
for var in "${required_vars[@]}"; do
  if [[ -z "${!var:-}" ]]; then
    missing+=("$var")
  fi
done

if [[ ${#missing[@]} -gt 0 ]]; then
  echo "ERROR: Missing required environment variables: ${missing[*]}" >&2
  exit 1
fi

mkdir -p /home/maya/.maya/outcomes
mkdir -p /home/maya/.maya/training
mkdir -p /app/logs

MODE="${1:-dev}"

cd /app/Agent

case "$MODE" in
  dev)
    echo "Starting Maya in dev mode..."
    exec python -m agent dev
    ;;
  console)
    exec python -m agent console
    ;;
  worker)
    exec python -m agent worker
    ;;
  *)
    echo "Unknown mode: $MODE. Valid: dev | console | worker" >&2
    exit 1
    ;;
esac

