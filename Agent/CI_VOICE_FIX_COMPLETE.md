# CI Voice Certification Fix Summary

## Changes Made

### 1. Fixed lk.chat Message Format (Critical Fix)
**File**: `scripts/verify_livekit_voice_roundtrip.py`

**Problem**: Was sending JSON payload to `lk.chat`:
```json
{"type": "probe_message", "content": "What is 2+2?", ...}
```

**Agent Expected**: Plain text that can be decoded:
```python
text = raw.decode("utf-8", errors="ignore").strip()
# Result: '{"type": "probe_message", "content": "What is 2+2?", ...}'
# Agent tried to process entire JSON as user input!
```

**Fix**: Send plain text directly:
```python
plain_text = spec.prompt.strip()
await room.local_participant.publish_data(
    plain_text.encode("utf-8"),
    topic="lk.chat",
)
```

### 2. Added lk.chat Echo Logging (Diagnostic)
**File**: `scripts/verify_livekit_voice_roundtrip.py`

Added logging for `lk.chat` echoes to verify messages are being received by room:
```python
if topic == "lk.chat":
    text = data.decode("utf-8", errors="ignore").strip()
    if text:
        print(f"event lk.chat_echo sender={sender} text={text[:60]}")
```

### 3. Enhanced send_message Response Detection
**File**: `scripts/verify_livekit_voice_roundtrip.py`

- Added comprehensive acceptance check for `send_message` HTTP response
- Extended timeout for HTTP fallback: `ACK_TIMEOUT_S + 3.0`
- Better logging to track which fallback is being used

### 4. Enhanced Data Event Logging (Diagnostic)
**File**: `scripts/verify_livekit_voice_roundtrip.py`

Added debug logging for ALL data_received events:
```python
if topic:
    print(f"event data_received topic={topic} sender={sender} size={len(data or b'')}")
```

---

## Root Cause Analysis

The "Greeting Works, Probes Fail" pattern indicates:

1. **Agent CAN speak** → TTS pipeline works
2. **Agent CAN receive data** → `lk.chat` messages are published
3. **Agent NOT responding** → Message format mismatch prevented processing

### Why JSON Format Failed

The agent's `_on_data_received` handler at `agent.py:2107`:
```python
text = raw.decode("utf-8", errors="ignore").strip()
```

With JSON payload, `text` became the entire JSON string:
```
'{"type": "probe_message", "content": "What is two plus two?", ...}'
```

The agent would then try to route/LLM process this entire string, which doesn't match any expected user intent patterns. The routing logic would fail or return no match, and no response would be generated.

### Why Plain Text Works

With plain text payload:
```python
text = "What is two plus two?"
```

This matches expected user input patterns, gets routed to the LLM, generates a response, and the response is published to `chat_events` topic.

---

## Expected Behavior After Fix

1. **Probe sends voice audio** (via `publish_pcm_audio`)
2. **If no STT transcription** (likely in CI):
   - Falls back to `send_message` HTTP endpoint
   - Backend publishes to room via `lk.chat` topic
3. **Agent receives `lk.chat` message** with plain text
4. **Agent processes message** through orchestrator
5. **Agent generates response** via LLM
6. **Agent publishes response** to `chat_events` topic
7. **Probe receives response** via `data_received` handler
8. **Probe evaluates** response against expected patterns
9. **Probe passes** if response contains expected content

---

## Testing Strategy

### Local Testing (Before CI)
```bash
# Terminal 1: Start agent
python agent.py worker

# Terminal 2: Run certification
python scripts/verify_livekit_voice_roundtrip.py \
  --timeout 90 \
  --health-url http://127.0.0.1:5050/health \
  --token-url http://127.0.0.1:5050/token \
  --send-message-url http://127.0.0.1:5050/send_message

# Watch for:
# - "event lk.chat_echo" showing received text
# - "event chat_event assistant_final" showing agent response
# - "probe_result ... PASS" for all 3 probes
```

### CI Testing
Trigger workflow dispatch on `main` branch. Monitor logs for:
- `lk.chat_sent` followed by `lk.chat_echo`
- `chat_event` with agent response
- `CERT_RESULT PASS`

---

## If Fix Doesn't Work

If probes still fail after this fix, investigate:

1. **Check if orchestrator is properly attached**
   - Look for log: `✅ [Phase 3] Shared orchestrator attached`
   - If missing, orchestrator initialization failed

2. **Check if agent receives lk.chat**
   - Look for log: `💬 [Phase X] lk.chat received from ...`
   - If missing, message routing issue

3. **Check if LLM generates response**
   - Look for log: `🤖 Triggering agent reply...`
   - If present but no response, LLM/generate_reply issue

4. **Check if response published**
   - Look for log: `event chat_event assistant_final ...`
   - If missing, publish_assistant_final failing

5. **Check agent state after greeting**
   - Greeting uses `session.say()` directly
   - Probes require orchestrator session
   - May need to verify `phase3_orchestrator.set_session(session)` succeeded

---

## Files Modified

1. `scripts/verify_livekit_voice_roundtrip.py` - Probe script with fixes

## Files to Monitor in CI

1. Agent logs for orchestrator initialization
2. Agent logs for lk.chat message handling
3. Agent logs for LLM response generation
4. Probe logs for acknowledgment detection

---

## Success Criteria

- [ ] `lk.chat_sent` appears in logs
- [ ] `lk.chat_echo` appears showing received text
- [ ] `chat_event assistant_final` appears with agent response
- [ ] All 3 probes show `PASS`
- [ ] `CERT_RESULT PASS` at end of run
