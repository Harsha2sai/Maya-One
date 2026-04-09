# Phase 28.6 Readiness Snapshot - 2026-04-09

## Decision
- Option C selected: lock and baseline Phase 28.6 before Phase 2 subagent runtime work.

## Timestamp
- Captured: 2026-04-09 19:34:19 IST

## Baseline Facts
- `Agent/core/orchestrator/agent_orchestrator.py` line count: **2640** (target < 4000)
- Depth staging: **depth=2 active**, **depth=3 gated**
- SQLite remains source of truth
- In-process message bus remains default transport

## Executed Validation Evidence

1. Prerequisite suites
```bash
pytest tests/test_agent_orchestrator.py tests/test_handoff_manager.py tests/test_message_bus.py tests/test_task_persistence.py tests/test_subagent_circuit_breaker.py -q
```
Result:
- `51 passed in 26.10s`

2. Compile check
```bash
python3 -m compileall core/
```
Result:
- Completed successfully (all `core/` packages listed, no compile failures)

3. Flag compatibility contract tests
```bash
pytest tests/test_settings.py -q
```
Result:
- `5 passed in 0.12s`

4. Recovery/idempotency drill evidence
```bash
pytest tests/test_task_store_sqlite.py::test_atomic_step_status_update_is_idempotent_for_duplicate_key tests/test_task_store_sqlite.py::test_claim_or_renew_does_not_reclaim_fresh_running_task -q
```
Result:
- `2 passed in 0.94s`

5. Message bus local publish latency SLO check
```bash
python3 - <<'PY'
import asyncio, time, statistics
from core.messaging.message_bus import MessageBus

async def main():
    bus = MessageBus(max_queue_depth=1000)
    async def handler(_):
        return None
    await bus.subscribe("agent.progress", handler)
    samples = []
    for i in range(200):
        t0 = time.perf_counter()
        await bus.publish("agent.progress", {"status": "running", "i": i}, trace_id="trace", task_id="task")
        samples.append((time.perf_counter() - t0) * 1000)
    avg = statistics.mean(samples)
    p95 = statistics.quantiles(samples, n=20)[18]
    p99 = statistics.quantiles(samples, n=100)[98]
    print(f"avg_ms={avg:.3f} p95_ms={p95:.3f} p99_ms={p99:.3f} max_ms={max(samples):.3f}")

asyncio.run(main())
PY
```
Result:
- `avg_ms=1.568 p95_ms=3.373 p99_ms=7.115 max_ms=9.616`
- Gate threshold `<100ms` local publish path: **PASS**

## Gate Status

### Gate 1 (Before Phase 2)
- Prereq suites green: **PASS**
- Queue bound + latency SLO `<100ms` verified: **PASS**
- Recovery drill with idempotent re-processing and claim guards: **PASS**
- Decision: **UNLOCKED for Phase 2 start**

### Gate 2 (Before Phase 3)
- Subagent lifecycle tests: **PENDING (Phase 2 deliverable)**
- Worktree isolation tests: **PENDING (Phase 2 deliverable)**
- Depth-2 soak >= 3 days: **PENDING**

### Gate 3 (Before Phase 4 / Depth-3 Consideration)
- Subagent families stable: **PENDING**
- Inter-agent load stability: **PENDING**
- Depth-2 soak >= 7 days: **PENDING**
- Fuzz loop with zero cycle escapes: **PENDING**

## Compatibility Lock Applied
- Internal flags retained:
  - `MULTI_AGENT_FEATURES_ENABLED`
  - `MULTI_AGENT_DEPTH3_ENABLED`
- Env aliases added and mapped:
  - `MAYA_SUBAGENTS` -> `MULTI_AGENT_FEATURES_ENABLED`
  - `MAYA_BACKGROUND` -> `MULTI_AGENT_DEPTH3_ENABLED`
- Precedence rule: internal names override aliases when both are set.

## Certification Payload
```json
{
  "phase_status": "CERTIFIED",
  "regressions": 0,
  "integration_status": "STABLE",
  "ready_for_next_phase": true
}
```
