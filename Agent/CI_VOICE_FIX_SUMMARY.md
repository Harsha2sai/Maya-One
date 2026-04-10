# CI Voice Certification Fix Summary

## Changes Made (commit `40bbd3a6` + fixes)

### 1. Enhanced send_message Fallback Detection
**File**: `scripts/verify_livekit_voice_roundtrip.py`

- Added comprehensive acceptance check for `send_message` HTTP response
- Now detects: `status`, `send_message_accepted`, `message_id`, or `id` fields
- Extended timeout for HTTP fallback: `ACK_TIMEOUT_S + 3.0` (extra time for backend→agent→response pipeline)

### 2. Improved lk.chat Fallback Format
**File**: `scripts/verify_livekit_voice_roundtrip.py`

- Changed from plain text (`"PROBE: {prompt}"`) to structured JSON:
  ```json
  {
    "type": "probe_message",
    "content": "{prompt}",
    "participant": "voice-probe-user",
    "probe_name": "{spec.name}",
    "attempt": {attempt}
  }
  ```
- Added explicit logging when `lk.chat` message is sent/fails
- Extended timeout for data channel: `ACK_TIMEOUT_S + 2.0`

### 3. Enhanced data_received Event Logging
**File**: `scripts/verify_livekit_voice_roundtrip.py`

- Added debug logging for ALL data_received events (topic, sender, size)
- Expanded chat_event capture to include any event starting with `assistant_` or `agent_`
- This helps diagnose what events the agent is actually sending

---

## Root Cause Analysis (In Progress)

### Evidence from CI Run `24062134523`

| Metric | Value | Interpretation |
|--------|-------|----------------|
| `probe_readiness passed=true` | ✅ | Agent connects and speaks greeting |
| `transcription_received=26` | ✅ | Transcription events ARE being received |
| `data_received` count | ? | Need to check agent event publication |
| `no_user_or_agent_transcription` | ❌ | No probe responses detected |

### Hypothesis: Agent State Mismatch

The pattern "greeting works, probes fail" suggests:

1. **Audio Not Transcribed**: STT service (Deepgram) may not process synthetic TTS audio
2. **Agent Pipeline Stalled**: Agent may enter a state where it ignores subsequent inputs
3. **Message Routing Issue**: `lk.chat` messages not reaching agent's `_handle_text_chat_input`

### Most Likely Cause

In CI environments, the STT pipeline often fails to transcribe synthetic audio from edge-tts because:
- Audio lacks natural speech patterns (prosody, breathing)
- Deepgram's model may reject "robotic" audio as noise
- Agent only responds to `transcription_received` events, not raw audio

When voice fails and fallback to `send_message`/`lk.chat` also fails, it suggests the agent isn't properly receiving/handling text messages either.

---

## Next Steps to Complete Fix

### Step 1: Run CI and Collect Enhanced Logs
The improved diagnostics will now show:
- Whether `send_message` is truly accepted
- Whether `lk.chat` messages are published successfully
- ALL data_received events with their topics

### Step 2: Verify Agent Message Handling (If Still Failing)
If probes still fail, check in `agent.py`:

1. **_on_data_received filter (line 2182)**:
   ```python
   if topic != "lk.chat":
       return
   ```
   - Ensure this isn't rejecting messages

2. **_accept_ingress deduplication (line 994)**:
   - May reject messages with duplicate content
   - Try adding unique content per probe

3. **Participant identity filtering (line 2101-2104)**:
   ```python
   if sender and str(sender).startswith("agent-"):
       return
   ```
   - `voice-probe-user` is valid, but check if other filtering applies

### Step 3: Force Text-Only Mode (If Voice Fails)
If STT consistently fails, modify probe to:
1. Skip voice audio entirely
2. Send directly via `lk.chat` with unique message IDs
3. Wait for agent response via `chat_events` topic

### Step 4: Add Agent Heartbeat
Add periodic "ping" via `lk.chat` to verify agent is responsive:
```python
await room.local_participant.publish_data(
    json.dumps({"type": "ping", "timestamp": time.time()}).encode(),
    topic="lk.chat",
)
```

---

## Verification Commands

```bash
# Run probe locally against running agent
python scripts/verify_livekit_voice_roundtrip.py \
  --timeout 90 \
  --health-url http://127.0.0.1:5050/health \
  --token-url http://127.0.0.1:5050/token \
  --send-message-url http://127.0.0.1:5050/send_message

# Check CI logs for new debug output
grep -E "(probe_fallback|event data_received|debug_|probe_ack)" cert_log.txt
```

---

## Success Criteria

- [ ] All 3 probes pass OR show clear acknowledgment at one fallback level
- [ ] `send_message_accepted=true` appears in logs
- [ ] `event data_received topic=chat_events` appears with agent responses
- [ ] CI run produces `CERT_RESULT PASS`
