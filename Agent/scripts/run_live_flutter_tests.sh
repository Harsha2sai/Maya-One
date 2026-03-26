#!/usr/bin/env bash

set -u -o pipefail

HEALTH_URL="http://localhost:5050/health"
SEND_URL="http://localhost:5050/send_message"
USER_ID="test_user"
RUN_ID="live_$(date +%Y%m%d_%H%M%S)_$RANDOM"

check_backend_health() {
  local code
  code="$(curl -s -o /tmp/maya_live_health.json -w "%{http_code}" "${HEALTH_URL}" || true)"
  if [[ "${code}" != "200" ]]; then
    echo "Backend health check failed."
    echo "Expected: ${HEALTH_URL} -> 200"
    echo "Got: ${code}"
    exit 1
  fi
  echo "Backend health check OK (200)."
}

check_send_message_endpoint() {
  local code
  code="$(curl -s -o /tmp/maya_live_send_preflight.json -w "%{http_code}" \
    -X POST "${SEND_URL}" \
    -H "Content-Type: application/json" \
    -d '{}' || true)"

  case "${code}" in
    400|409)
      echo "send_message preflight OK (route reachable, status=${code})."
      ;;
    404|000)
      echo "send_message preflight failed (status=${code})."
      echo "Expected route: ${SEND_URL}"
      exit 1
      ;;
    *)
      echo "send_message preflight returned status=${code} (continuing)."
      ;;
  esac
}

confirm_flutter_connected() {
  local ans
  echo
  read -r -p "Is the Flutter app connected and visible for live verification? (y/N): " ans
  case "${ans}" in
    y|Y|yes|YES)
      echo "Proceeding with live message sequence."
      ;;
    *)
      echo "Aborted. Connect Flutter app first, then run again."
      exit 1
      ;;
  esac
}

send_message() {
  local message="$1"
  local code
  local body

  echo ">>> Sending: ${message}"
  body="$(printf '{"message":"%s","user_id":"%s","run_id":"%s"}' \
    "${message//\"/\\\"}" "${USER_ID}" "${RUN_ID}")"
  code="$(curl -s -o /tmp/maya_live_send.json -w "%{http_code}" \
    -X POST "${SEND_URL}" \
    -H "Content-Type: application/json" \
    -d "${body}" || true)"

  if [[ "${code}" != "200" ]]; then
    echo "WARN: send_message returned HTTP ${code} for message: ${message}"
    [[ -s /tmp/maya_live_send.json ]] && echo "Response: $(cat /tmp/maya_live_send.json)"
  fi

  sleep 6
  echo "<<< Check Flutter UI now"
  sleep 3
}

send_fast_lane_queue_triplet() {
  local messages=("hello" "what time is it" "who are you")
  local msg

  echo "PHASE 10 - Lane queue (fast triplet)"
  for msg in "${messages[@]}"; do
    local body
    local code
    echo ">>> Sending: ${msg}"
    body="$(printf '{"message":"%s","user_id":"%s","run_id":"%s"}' \
      "${msg//\"/\\\"}" "${USER_ID}" "${RUN_ID}")"
    code="$(curl -s -o /tmp/maya_live_send.json -w "%{http_code}" \
      -X POST "${SEND_URL}" \
      -H "Content-Type: application/json" \
      -d "${body}" || true)"
    if [[ "${code}" != "200" ]]; then
      echo "WARN: send_message returned HTTP ${code} for message: ${msg}"
      [[ -s /tmp/maya_live_send.json ]] && echo "Response: $(cat /tmp/maya_live_send.json)"
    fi
    sleep 0.5
  done

  sleep 6
  echo "<<< Check Flutter UI now"
  sleep 3
}

run_all_phases() {
  echo
  echo "PHASE 1 - Identity"
  send_message "what is your name"
  send_message "what can you do"

  echo
  echo "PHASE 2 - Fast path"
  send_message "what time is it"
  send_message "pause"

  echo
  echo "PHASE 3 - Research"
  send_message "what is quantum computing"
  send_message "who is the current CEO of OpenAI"

  echo
  echo "PHASE 4 - Media"
  send_message "play some music"
  send_message "next track"

  echo
  echo "PHASE 5 - System"
  send_message "take a screenshot"
  send_message "list open windows"

  echo
  echo "PHASE 6 - Memory"
  send_message "my name is Harsha"
  send_message "what is my name"

  echo
  echo "PHASE 7 - Tasks"
  send_message "set a reminder to check email in 10 minutes"

  echo
  echo "PHASE 8 - Chat"
  send_message "tell me a joke"

  echo
  echo "PHASE 9 - TTS check"
  send_message "say hello out loud"

  echo
  send_fast_lane_queue_triplet
}

main() {
  check_backend_health
  check_send_message_endpoint
  confirm_flutter_connected
  run_all_phases
  echo
  echo "All 10 phases sent. Review Flutter UI for responses."
  echo "Check Agent/logs for routing decisions."
}

main "$@"
