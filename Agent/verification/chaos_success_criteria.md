# Chaos Experiment Success Criteria

Define what "success" means before breaking anything.

## Universal Invariants (All Experiments)

### System Survival
- ✅ Agent continues responding to user input
- ✅ No unhandled exceptions or crashes
- ✅ Boot gate remains active
- ✅ Runtime probes remain active

### Safety
- ✅ Zero probe violations during chaos
- ✅ Verification suite remains runnable
- ✅ Telemetry continues logging
- ✅ Guardrails enforce limits

## Experiment-Specific Criteria

### 1. Latency Injection

| Criterion | Target |
|-----------|--------|
| **System Survival** | Agent responds within critical threshold (8s) |
| **User Experience** | Graceful degradation, no silent failures |
| **Safety** | No probe violations |
| **Recovery** | < 3 turns to return below warning |

**Pass Condition**: System handles 2x baseline latency without crashing.

---

### 2. Rate Limit Simulation

| Criterion | Target |
|-----------|--------|
| **System Survival** | Retry logic activates correctly |
| **User Experience** | Retry count < 5 attempts |
| **Safety** | No probe violations |
| **Recovery** | < 5 turns after rate limit clears |

**Pass Condition**: System backs off and recovers without user-visible errors.

---

### 3. Tool Execution Failures

| Criterion | Target |
|-----------|--------|
| **System Survival** | Fallback to LLM explanation |
| **User Experience** | Clear error message to user |
| **Safety** | No probe violations |
| **Recovery** | Immediate (next turn) |

**Pass Condition**: Tool failures don't cascade into system failures.

---

### 4. Memory Pressure (High Context)

| Criterion | Target |
|-----------|--------|
| **System Survival** | Context truncation activates |
| **User Experience** | Latency < critical threshold |
| **Safety** | No probe violations |
| **Recovery** | < 5 turns as context shrinks |

**Pass Condition**: System handles 2x baseline context without OOM.

---

### 5. Long Session Drift

| Criterion | Target |
|-----------|--------|
| **System Survival** | Agent remains coherent for 20+ turns |
| **User Experience** | No degradation in response quality |
| **Safety** | No probe violations |
| **Recovery** | N/A (steady state) |

**Pass Condition**: Metrics remain stable over extended conversation.

---

## Kill Switch Conditions

Automatically stop experiment if:
- ❌ Probe failures > 3
- ❌ Latency > critical for 5 consecutive turns
- ❌ Retry count > 5
- ❌ Token budget exceeded
- ❌ Session duration > 300s
- ❌ Consecutive failures > 10

## Measurement Protocol

For each experiment:
1. Capture baseline metrics (3 normal turns)
2. Inject failure
3. Measure degradation depth
4. Measure recovery time
5. Validate safety layers active
6. Export tagged telemetry

**Success = All criteria met + No kill switch triggers**
