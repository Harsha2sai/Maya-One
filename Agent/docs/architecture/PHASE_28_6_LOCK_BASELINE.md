# Phase 28.6 Phase-1 Lock Baseline

Date: 2026-04-09
Decision: Option C (lock and baseline Phase 28.6 before Phase 2 runtime work)
Status: Locked for additive-only follow-up work

## Scope Locked

This document freezes the Phase 28.6 prerequisite contracts as the authoritative baseline for Phase 2+ implementation.

- Handoff depth staging: depth=2 active, depth=3 gated.
- Queue caps and operational guardrails.
- Task persistence and recovery markers.
- In-process message bus envelopes and bounded queues.
- Progress event bridge with throttling + terminal-event bypass.
- Poison/idempotency policy in task runtime.

## Contract Baseline (Authoritative)

1. Handoff depth gates
- Source: `core/agents/handoff_manager.py`
- `MAX_DEPTH_STAGE_A = 2` (default active)
- `MAX_DEPTH_STAGE_B = 3` (enabled only when depth-3 flag is true)
- Runtime switch: `multi_agent_depth3_enabled`

2. Multi-agent feature flags (internal + compatibility aliases)
- Source: `config/settings.py`
- Internal flags (authoritative):
  - `MULTI_AGENT_FEATURES_ENABLED` -> `settings.multi_agent_features_enabled`
  - `MULTI_AGENT_DEPTH3_ENABLED` -> `settings.multi_agent_depth3_enabled`
- Compatibility aliases (docs-facing):
  - `MAYA_SUBAGENTS` (fallback alias for `MULTI_AGENT_FEATURES_ENABLED`)
  - `MAYA_BACKGROUND` (fallback alias for `MULTI_AGENT_DEPTH3_ENABLED`)
- Precedence rule: internal names win if both internal and alias are set.

3. Queue and concurrency caps
- Source: `config/settings.py`, `core/agents/handoff_manager.py`, `core/messaging/message_bus.py`
- `MAX_PENDING_HANDOFFS_PER_SESSION` (default 10)
- `MAX_CONCURRENT_SUBAGENTS_PER_MAYA` (default 5)
- `MAX_MESSAGE_BUS_QUEUE_DEPTH_GLOBAL` (default 1000)
- Exceeded caps return structured limit failures (`handoff_*_limit_exceeded`, `message_bus_queue_limit_exceeded`).

4. Persistence and recovery markers
- Source: `core/tasks/task_persistence.py`
- Checkpoint write contract: `save_checkpoint(task_id, step_id, payload, checkpoint_id?, ts?)`
- Resume marker contract: `mark_resumed(task_id, worker_id)`
- Terminal marker contract: `mark_terminal(task_id, status, reason)`
- SQLite remains source of truth in this phase.

5. Message envelope contract
- Source: `core/messaging/message_bus.py`
- Envelope fields: `channel`, `payload`, `trace_id`, `handoff_id`, `task_id`, `message_id`, `timestamp`, `checkpoint_id`, `metadata`
- Correlation IDs are mandatory in delegated paths.

6. Progress bridge contract
- Source: `core/messaging/progress_stream.py`
- Per-session throttle: `MAX_PROGRESS_EVENTS_PER_SEC_PER_SESSION` (default 10)
- Terminal statuses (`completed`, `failed`, `cancelled`) bypass throttle.

7. Poison + idempotency policy
- Source: `core/tasks/task_worker.py`, `core/tasks/atomic_task_state.py`
- Step execution uses idempotency key: `task_id:step_index:retry_count`
- Duplicate key execution is suppressed and treated as safe idempotent behavior.
- Terminal poison conditions mark task as failed and emit `task_poisoned` event.

## Governance Rules for Phase 2 Start

- All changes must be additive and backward compatible against this baseline.
- Depth-3 remains disabled until explicit unlock gates pass.
- Lineage fields (`parent_handoff_id`, `delegation_chain_id`) must be propagated in all delegated requests.
- Exactly-once side-effect semantics must remain intact across checkpoint/resume paths.

## Readiness Snapshot

See `obsidian_vault/Reports/Phase-28.6-Readiness-Snapshot-2026-04-09.md` for executable evidence and gate status.
