#!/usr/bin/env bash

set -euo pipefail

HEALTH_URL="http://localhost:5050/health"
TOKEN_URL="http://localhost:5050/token"
SEND_URL="http://localhost:5050/send_message"
PROMPT="${1:-what is your name}"
USER_ID="smoke_user"
RUN_ID="smoke_$(date +%Y%m%d_%H%M%S)_$RANDOM"
LOG_PATH="${MAYA_BACKEND_LOG:-}"
ROOM_NAME="${MAYA_SMOKE_ROOM:-smoke_room_${RUN_ID}}"

if [[ -z "${LOG_PATH}" ]]; then
  echo "FAIL: set MAYA_BACKEND_LOG to the backend agent_full.log path"
  exit 1
fi

if [[ ! -f "${LOG_PATH}" ]]; then
  echo "FAIL: backend log not found at ${LOG_PATH}"
  exit 1
fi

health_code="$(curl -s -o /tmp/maya_smoke_health.json -w "%{http_code}" "${HEALTH_URL}" || true)"
if [[ "${health_code}" != "200" ]]; then
  echo "FAIL: backend health check returned ${health_code}"
  exit 1
fi

token_payload="$(printf '{"roomName":"%s","participantName":"%s","metadata":{"source":"smoke_flutter_roundtrip","run_id":"%s"}}' \
  "${ROOM_NAME}" "${USER_ID}" "${RUN_ID}")"
if [[ "${MAYA_USE_EXISTING_ROOM_CONTEXT:-0}" != "1" ]]; then
  token_code="$(curl -s -o /tmp/maya_smoke_token.json -w "%{http_code}" \
    -X POST "${TOKEN_URL}" \
    -H "Content-Type: application/json" \
    -d "${token_payload}" || true)"
  if [[ "${token_code}" != "200" ]]; then
    echo "FAIL: token issue returned ${token_code}"
    [[ -s /tmp/maya_smoke_token.json ]] && cat /tmp/maya_smoke_token.json
    exit 1
  fi
fi

preflight_code="$(curl -s -o /tmp/maya_smoke_preflight.json -w "%{http_code}" \
  -X POST "${SEND_URL}" \
  -H "Content-Type: application/json" \
  -d '{}' || true)"
case "${preflight_code}" in
  400|409) ;;
  404|000)
    echo "FAIL: /send_message unavailable (${preflight_code})"
    exit 1
    ;;
  *)
    echo "WARN: /send_message preflight returned ${preflight_code}"
    ;;
esac

if [[ "${MAYA_ASSUME_CONNECTED:-0}" != "1" ]]; then
  read -r -p "Is Flutter connected to this backend right now? (y/N): " connected
  case "${connected}" in
    y|Y|yes|YES) ;;
    *)
      echo "FAIL: Flutter not confirmed connected"
      exit 1
      ;;
  esac
fi

start_line="$(wc -l < "${LOG_PATH}")"
payload="$(printf '{"message":"%s","user_id":"%s","run_id":"%s"}' \
  "${PROMPT//\"/\\\"}" "${USER_ID}" "${RUN_ID}")"
send_code=""
for attempt in 1 2 3; do
  send_code="$(curl -s -o /tmp/maya_smoke_send.json -w "%{http_code}" \
    -X POST "${SEND_URL}" \
    -H "Content-Type: application/json" \
    -d "${payload}" || true)"
  if [[ "${send_code}" == "200" ]]; then
    break
  fi
  if [[ "${send_code}" == "400" || "${send_code}" == "409" ]]; then
    sleep 2
    continue
  fi
  break
done

if [[ "${send_code}" != "200" ]]; then
  echo "FAIL: send_message returned ${send_code}"
  [[ -s /tmp/maya_smoke_send.json ]] && cat /tmp/maya_smoke_send.json
  exit 1
fi

found_router=0
found_final=0
found_send=0
max_wait="${MAYA_STRICT_WAIT_SECONDS:-45}"
for _ in $(seq 1 "${max_wait}"); do
  new_logs="$(sed -n "$((start_line + 1)),\$p" "${LOG_PATH}")"
  if grep -Eiq "send_message_accepted" <<< "${new_logs}"; then
    found_send=1
  fi
  if grep -Eiq "agent_router_decision" <<< "${new_logs}"; then
    found_router=1
  fi
  if grep -Eiq "chat_event_published topic=chat_events type=assistant_final" <<< "${new_logs}"; then
    found_final=1
  fi
  if [[ "${MAYA_REQUIRE_ROUTING:-0}" == "1" ]]; then
    if [[ "${found_router}" == "1" && "${found_final}" == "1" ]]; then
      echo "PASS: roundtrip verified (router decision + assistant_final published)"
      exit 0
    fi
  elif [[ "${found_send}" == "1" ]]; then
    echo "PASS: bridge verified (send_message_accepted observed)"
    exit 0
  fi
  if [[ "${found_router}" == "1" && "${found_final}" == "1" && "${MAYA_REQUIRE_ROUTING:-0}" != "1" ]]; then
    echo "PASS: roundtrip verified (router decision + assistant_final published)"
    exit 0
  fi
  sleep 1
done

if [[ "${MAYA_REQUIRE_ROUTING:-0}" == "1" ]]; then
  echo "FAIL: strict roundtrip signal not observed in backend log"
  echo "INFO: ensure Flutter participant is connected to the same backend room."
else
  echo "FAIL: bridge signal not observed in backend log"
fi
echo "--- recent log tail ---"
tail -n 80 "${LOG_PATH}" || true
exit 1
