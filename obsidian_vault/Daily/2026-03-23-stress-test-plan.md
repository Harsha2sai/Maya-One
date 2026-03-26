---
tags: [daily-note, stress-test, certification, phase-10]
date: "2026-03-23"
---

# Daily Note: 2026-03-23 (Monday)

## Maya Stress Test Certification Plan

**Objective**: Run the 14-level stress test plan in 9 batches to certify Maya for Phase 10A release.

**Resource constraints**: Running on 11 GiB RAM system with 584 MiB free, 4 CPU cores

**Approach**: Serial batch execution - only one heavy runtime active at a time using one-shot console runs where possible

---

## Batch Plan Summary

| Batch | Phase | Scenarios | Type |
|-------|-------|-----------|------|
| 0 | Preflight | - | Setup |
| 1 | Console Stateless Light | 12 scenarios (1A, 2A, 2B, 3A, 3B, 4B, 6A, 7A, 7B, 8A, 8B, 14B) | One-shot console runs |
| 2 | Research Heavy | 3 scenarios (4A, 6B, 14A) | Research-intensive |
| 3 | Stateful Pronoun | 2 scenarios (5A, 5B) | Persistent console |
| 4 | Planner Task Execution | 2 scenarios (9A, 9B) | Task store interaction |
| 5 | Stateful Memory | 2 scenarios (10A, 10B) | Memory interaction |
| 6 | ContextGuard Stress | 2 scenarios (11A, 11B) | Context pressure tests |
| 7 | Provider Resilience | 2 scenarios (12A, 12B) | TTS fallback tests |
| 8 | Flutter Integration | 3 scenarios (1B, 13A, 13B) | Backend + Flutter together |
| 9 | Final Audit | - | Regression greps & report generation |

**Total levels**: 14 levels spanning 26 scenarios

---

## Execution Sequence

### Batch 0: Preflight Setup ✓
**Status:** Pending

**Steps:**
1. Verify audit log exists: `test -f logs/audit.log`
2. Capture baseline line counts: `wc -l logs/audit.log`
3. Capture TTS/provider state: `grep "tts_provider_active" logs/audit.log | tail -3`

**Expected results:**
- Audit log exists
- No old runtime processes active

---

### Batch 1: Console Stateless Light Cases (Phase 1)
**Status:** Pending | **Scenarios:** 12 one-shot runs

**Levels to test:** 1A, 2A, 2B, 3A, 3B, 4B, 6A, 7A, 7B, 8A, 8B, 14B

**Execution commands:**
```bash
# Example run for each scenario
run_case l1a "what is your name"
run_case l2a "what time is it"
run_case l2b "pause"
run_case l3a "what can you do"
run_case l3b "hi"
run_case l4b "tell me a joke"
run_case l6a "open firefox"
run_case l7a "set a reminder to drink water in 30 minutes"
run_case l7b "remind me to call John"
run_case l8a "play some jazz music"
run_case l8b "set volume to 60 percent"
run_case l14b "take a screenshot"
```

**Checks after each:**
- Search audit file for expected signals:
  - `routing_mode=deterministic_fast_path`
  - `handoff_requested target=scheduling`
  - `handoff_accepted target=media confidence=1.000 reason=media_play_intent`

**Stop conditions:**
- Any one-shot case crashes
- Raw exception in user-facing output
- Fast-path scenario unexpectedly routes through handoff
- Handoff scenario unexpectedly skips handoff

---

### Batch 2: Research Heavy Cases (Phase 2)
**Status:** Pending | **Scenarios:** 3 research-intensive

**Levels to test:** 4A, 6B, 14A

**Execution commands:**
```bash
run_case l4a "who is the current president of France"
run_case l6b "search the web for latest news about AI"
run_case l14a "search for information about quantum computing and set a reminder to read the results tomorrow morning"
```

**Required checks:**
- `agent_router_decision`
- `handoff_requested`
- `handoff_completed`
- `research_pipeline_mode=inline_main`
- Clean `tts_voice_summary`
- No `handoff_depth_exceeded`

**Stop conditions:**
- Research doesn't complete cleanly
- Scheduling fails after research (Level 14A)
- Response contains markdown/JSON/tool markup

---

### Batch 3: Stateful Pronoun Tests (Phase 3)
**Status:** Pending | **Scenarios:** 2 (requires persistent console)

**Levels to test:** 5A, 5B

**Execution:**
```bash
./venv/bin/python agent.py console
```

Then execute within same session:
- 5A Turn 1: "who is the prime minister of Japan"
- 5A Turn 2: "tell me more about him"
- 5B: Send research query, wait 95s, then "tell me more about him"

**Required checks:**
- 5A shows `pronoun_followup_rewrite`
- 5B does NOT show `pronoun_followup_rewrite`
- No fallback reset text like "This conversation has just begun"

**Evidence capture:**
```bash
# Before session: note audit line count
snapshot_audit

# After: capture delta
 tail -n +"$((START+1))" logs/audit.log > /tmp/maya_stress/l5.audit
 ```

---

### Batch 4: Planner Task Execution (Phase 4)
**Status:** Pending | **Scenarios:** 2 (task store interaction)

**Levels to test:** 9A, 9B

**Execution:**
```bash
# One-shot runs
run_case l9a "set a reminder to check my email in 10 minutes and then open Chrome"
run_case l9b "create a task to research quantum computing and summarize the findings"
```

**Required checks:**
- `planner_deterministic_plan_applied` for 9A
- `plan_ms=0` for deterministic planning
- Task plan contains both `set_reminder` and `open_app`
- `create_task` path and TaskStore write for 9B
- Worker execution begins
- No planner schema error

**Additional evidence:** Inspect TaskStore state if needed

---

### Batch 5: Stateful Memory Tests (Phase 5)
**Status:** Pending | **Scenarios:** 2 (memory interaction)

**Levels to test:** 10A, 10B

**Execution:**
```bash
./venv/bin/python agent.py console
```

Send in order:
1. "my name is Harsha and I work on AI systems"
2. "what do you know about me"
3. "do you remember what I told you about myself"

**Required checks:**
- Memory write/store log on turn 1
- Retrieval on turns 2 and 3
- Response mentions "Harsha" and "AI systems"
- No identity/small-talk memory skip on recall turns

---

### Batch 6: ContextGuard Stress (Phase 6)
**Status:** Pending | **Scenarios:** 2 (context pressure)

**Levels to test:** 11A (15-turn conversation), 11B (500+ word summary)

**Execution:**
```bash
./venv/bin/python agent.py console
```

**11A**: Send 15 varied turns mixing identity/chat, research, scheduling, media, memory follow-up, tool requests

**11B**: Paste one 500+ word block and ask for summary

**Post-batch checks:**
```bash
grep "context_guard_hard_limit_reached" logs/audit.log
grep "context_guard_tier3_summarizer" logs/audit.log
grep "context_guard_tier4_trimmed" logs/audit.log
grep "context_guard_tier2_long_turn" logs/audit.log
```

**Required checks:**
- Zero hard-limit hits
- At least one Tier 3 summarizer hit
- Tier 2 long-turn hit for large message
- Summary returned successfully

---

### Batch 7: Provider Resilience (Phase 7)
**Status:** Pending | **Scenarios:** 2 (TTS fallback)

**Levels to test:** 12A, 12B

**12A - Boot log check:**
```bash
grep "tts_provider_active" logs/audit.log | tail -3
grep "provider_supervisor_active" logs/audit.log | tail -3
```

**12B - Synthetic TTS failure:**
```bash
start=$(snapshot_audit)
env ELEVENLABS_API_KEY=invalid timeout 35 ./venv/bin/python agent.py console <<< "what time is it" > /tmp/maya_stress/l12b.out 2>&1
 tail -n +"$((start+1))" logs/audit.log > /tmp/maya_stress/l12b.audit
 ```

** Required checks: **
- `circuit_breaker_open provider=api.elevenlabs.io` or `tts_fallback_triggered`
- `edge_tts_promoted_to_primary reason=all_primary_providers_failed`
- `tts_provider_active provider=edge_tts`
- Response still delivered

** Stop condition: ** If process crashes instead of falling back, stop certification

---

### Batch 8: Flutter Integration (Phase 8)
** Status: ** Pending | ** Scenarios: ** 3 (backend + Flutter together)

** Levels to test: ** 1B, 13A, 13B

** Process model** (only these heavy processes active):
- Backend worker
- Flutter Linux desktop app

**Backend worker** (from `Agent/`):
```bash
./venv/bin/python agent.py dev
```

**Flutter app** (from `agent-starter-flutter-main/`):
```bash
flutter run -d linux \
  --dart-define=FLUTTER_GATEKEEPER_MODE=true \
  --dart-define=FLUTTER_GATEKEEPER_LOG_PATH=/tmp/maya_flutter_gatekeeper.jsonl
```

**Test sequence:**
- 1B: Connect and wait for greeting
- 13A: Multi-turn conversation (research, reminder, media, knowledge)
- 13B: Reconnect test (send, stop backend, restart, send again)

**Evidence capture:**
```bash
grep "schema_version_mismatch" /tmp/maya_flutter_gatekeeper.jsonl
grep "agent_thinking" /tmp/maya_flutter_gatekeeper.jsonl | tail
grep "tool_execution" /tmp/maya_flutter_gatekeeper.jsonl | tail
grep "agent_speaking" /tmp/maya_flutter_gatekeeper.jsonl | tail
grep "turn_complete" /tmp/maya_flutter_gatekeeper.jsonl | tail
grep "bootstrap_context_applied" /tmp/maya_flutter_gatekeeper.jsonl | tail
```

**Required checks:**
- Greeting appears
- All states surface: thinking, tool execution, research pending, speaking, turn complete
- No `schema_version_mismatch`
- Reconnect works
- `bootstrap_context_applied` appears after reconnect
- No stale transcript leakage

**Cleanup:** Stop backend and Flutter before Batch 9

---

### Batch 9: Final System Audit (Phase 9)
**Status:** Pending | **Scenarios:** Regression greps & report generation

**Final audit command:**
```bash
cd /home/harsha/Downloads/Projects/v2/Maya-One-phase-0-2/Agent
echo "=== REGRESSION GREPS ==="
echo "--- Hard limit (should be 0) ---"
grep -c "context_guard_hard_limit_reached" logs/audit.log
echo "--- Schema mismatch (should be 0) ---"
grep -c "schema_version_mismatch" logs/audit.log
echo "--- Deprecated research agent (should be 0) ---"
grep -c "research_agent_deprecated_path_used" logs/audit.log
echo "--- Duplicate trace_id bug (should be 0) ---"
grep "handoff_completed" logs/audit.log | grep -c "trace_id=.*trace_id="
echo "=== POSITIVE SIGNALS ==="
echo "--- ElevenLabs as primary TTS ---"
grep "tts_provider_active" logs/audit.log | grep -c "provider=elevenlabs"
echo "--- Inline research pipeline active ---"
grep -c "research_pipeline_mode=inline_main" logs/audit.log
echo "--- HandoffManager used for sub-agents ---"
grep -c "handoff_completed" logs/audit.log
echo "--- Fast-path working ---"
grep -c "routing_mode=deterministic_fast_path" logs/audit.log
echo "--- Pronoun rewrite fired ---"
grep -c "pronoun_followup_rewrite" logs/audit.log
echo "=== PROVIDER SUPERVISOR ==="
grep "provider_supervisor_active" logs/audit.log | tail -1
echo "=== DONE ==="
```

**Expected final counts:**
- Hard limit: 0
- Schema mismatch: 0
- Deprecated research agent: 0
- Duplicate trace_id: 0
- All positive signals: > 0
- Provider supervisor: visible and active

**Final report must include:**
1. Batch-by-batch PASS/FAIL status
2. Level-by-level PASS/FAIL status
3. The full final audit grep output
4. Unexpected log lines observed
5. Certification decision: ** Ready for Phase 10A ** or ** Not Ready **

** Critical failures (stop immediately):**
- Backend crash
- Flutter freeze
- OOM symptoms or swap thrash
- `context_guard_hard_limit_reached`
- `schema_version_mismatch`
- duplicate `trace_id` bug reappears
- Specialist handoff returns wrong target/reason

---

## Test Coverage Summary

** Core functionality: ** Batches 1, 2, 4, 8
** Edge cases: ** Batches 3, 6, 7
** Failure recovery: ** Batches 7, 8, 1
** Latency stress: ** Batches 1, 6
** Memory interaction: ** Batches 5, 6
** Tool invocation: ** Batches 1, 2, 4
** Multi-turn conversation: ** Batches 3, 5, 8
** Cross-surface consistency: ** Batch 8

---

## Acceptance Criteria

System ready for Phase 10A ** ONLY IF **
- Every batch passes
- Every original level and scenario passes
- Final regression grep counts are all zero
- Flutter reconnect succeeds cleanly
- No raw exceptions reach user
- No response contains raw JSON/markdown/tool markup
- No unexpected critical log lines appear

---

## Implementation Notes

** Resource Control Rules:**
- Never run > 1 heavy runtime at same time (console, dev, Flutter)
- Close previous batch before starting next
- Prefer one-shot runs for stateless scenarios
- Record only log deltas
- Keep Flutter validation in one dedicated batch

**Required helper aliases:**
```bash
# Run case helper
run_case() {
  local case_id="$1"
  local prompt="$2"
  local start
  start=$(wc -l < logs/audit.log 2>/dev/null || echo 0)
  timeout 35 ./venv/bin/python agent.py console <<< "$prompt" > "/tmp/maya_stress/${case_id}.out" 2>&1
  tail -n +"$((start+1))" logs/audit.log > "/tmp/maya_stress/${case_id}.audit"
}

# Snapshot helper
snapshot_audit() {
  wc -l < logs/audit.log 2>/dev/null || echo 0
}
```

**Expected total execution time:** 1-2 hours (serial execution)

**Next step**: Execute Batch 0 (Preflight) to begin certification

---

*Plan created: 2026-03-23*
*System: Maya-One Phase 9 completed*
*Target: Phase 10A readiness*
