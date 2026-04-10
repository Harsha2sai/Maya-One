# CI Voice Certification Probe Fix Plan

## Problem Summary

**Status**: CI voice certification fails with `no_user_or_agent_transcription` for all 3 probes.

**Key Evidence**:
- `send_message` fallback IS accepted by backend (`send_message_accepted` appears)
- Events show ONLY greeting transcriptions (`transcription_received=10`)
- NO post-probe agent/user transcription events in CI
- Local verification PASSES consistently

**Root Cause Hypothesis**:
The agent enters an "Echo" state or transcription pipeline stalls after initial greeting in the slower/more constrained CI environment.

---

## Fix Strategy

### Phase 1: Environment & Timing Stabilization (Priority: CRITICAL)

1. **Increase Greeting Settle Time**
   - Current: Waits for 2 stable loops after seeing agent transcript
   - Problem: CI runners are slower; agent may not be fully ready
   - Fix: Add minimum 5-second delay AFTER agent transcript detected before first probe
   - File: `scripts/verify_livekit_voice_roundtrip.py:619-636`

2. **Add Post-Greeting Health Check**
   - Before injecting first probe, verify agent is responsive
   - Send a lightweight ping/data message and wait for acknowledgment
   - This proves the agent pipeline is live beyond just transcription

3. **Extend Collection Windows**
   - Current: `collect_seconds=18-24s` per probe
   - Problem: CI runners have higher latency
   - Fix: Increase to `collect_seconds=30s` for CI environments
   - Use env var `CI=true` to detect CI environment

### Phase 2: Fallback Strategy Enhancement (Priority: HIGH)

4. **Implement Multi-Modal Fallback Chain**
   Current fallback (single attempt):
   ```
   voice audio → send_message HTTP → lk.chat data channel
   ```

   Enhanced fallback (retry loop):
   ```
   voice audio (attempt 1)
   → wait 3s
   → send_message HTTP (attempt 2)
   → wait 3s
   → lk.chat with explicit "PROBE:" prefix (attempt 3)
   → wait 3s
   → direct data channel publish with metadata (attempt 4)
   ```

5. **Add Fallback Acknowledgment Detection**
   - After each fallback, wait for specific acknowledgment event
   - If no ack within 5s, escalate to next fallback level
   - Log which fallback level succeeded for diagnostics

### Phase 3: Diagnostics & Traceability (Priority: HIGH)

6. **Add CI-Specific Debug Logging**
   - Log full transcription history at each probe attempt
   - Log agent state transitions (connected → ready → responding)
   - Log timing deltas between events for latency analysis

7. **Capture Room State Snapshots**
   - Before each probe, dump:
     - Remote participant count
     - Track subscription status
     - Data channel connection state
   - This reveals if CI has connection issues not seen locally

8. **Add Transcription Timeout Detection**
   - If no transcription received within 10s of audio injection, log warning
   - This helps distinguish between "agent didn't hear" vs "agent didn't respond"

### Phase 4: Alternative Injection Methods (Priority: MEDIUM)

9. **Implement Direct Chat Message API**
   - If voice audio fails consistently, bypass voice pipeline entirely
   - Use a dedicated `/probe` endpoint that sends text directly to agent
   - This validates the agent logic separately from the voice pathway

10. **Pre-Probe Warmup Sequence**
    - Send a "warmup" message before actual probes
    - This forces the agent to initialize all pipelines
    - Discard warmup response, proceed with real probes

---

## Implementation Order

```
Step 1: Add timing buffers and CI detection (Phase 1)
        ↓
Step 2: Implement enhanced logging (Phase 3)
        ↓
Step 3: Test in CI to gather diagnostic data
        ↓
Step 4: Based on diagnostics, implement fallback chain (Phase 2)
        ↓
Step 5: Final validation and tag v0.28.0
```

---

## Acceptance Criteria

- [ ] All 3 probes pass in CI with voice audio (no fallback needed)
- [ ] OR fallback chain successfully delivers messages when voice fails
- [ ] CI run produces detailed logs showing agent state transitions
- [ ] Documented timing differences between local and CI environments
- [ ] `v0.28.0` tag created after 3 consecutive successful CI runs

---

## Files to Modify

1. `scripts/verify_livekit_voice_roundtrip.py` - Main probe logic
2. `.github/workflows/phase27-cert.yml` - CI workflow (add debug artifacts)
3. `api/handlers.py` - Add `/probe` endpoint for direct text injection (optional)

---

## Testing Strategy

1. Run probe script locally with `--timeout` flags to simulate CI slowness
2. Add artificial delays in local agent to reproduce CI behavior
3. Use GitHub Actions debug logging for CI troubleshooting
4. Consider using `tmate` or similar for interactive CI debugging if needed
