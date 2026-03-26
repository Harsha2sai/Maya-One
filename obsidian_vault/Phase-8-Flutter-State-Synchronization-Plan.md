# Phase 8: Flutter Frontend State Synchronization

**Status:** Ready for Implementation
**Phase:** 8
**Estimated Timeline:** 10-12 working days
**Scope:** Focused sync phase (no architecture rewrite)

---

## Summary

Phase 8 is a **targeted frontend sync phase** that makes Flutter UI correctly reflect agent state for the critical user path: research completion, confirmation flows, tool execution, and reconnect handling.

The backend event schema and validation system is already complete. The main gap is that `AgentActivityController` is missing completion handlers and does not properly clear stale state during reconnect/bootstrap transitions.

**Phase 8 does:**
1. Fix reconnect/bootstrap cleanup in `AgentActivityController`
2. Add missing high-value event handlers for result/completion events
3. Verify existing UI surfaces (already wired to `AgentActivityController`) reflect correct state
4. Add focused tests for critical user paths

**Phase 8 does NOT:**
- Migrate `ChatProvider` authority
- Add `EventLifecycleManager` or complex ordering logic
- Remove `ChatProvider.agentState` (backward compatibility preserved)
- Handle broad out-of-order scenarios (deferred to Phase 8.5)
- Change backend schema

---

## Current Grounded State

### Already Implemented
- ✅ `SessionProvider` validates events and emits `AgentUiEvent`
- ✅ Schema mismatches logged as `schema_version_mismatch`
- ✅ `ChatProvider` handles all transcript rendering
- ✅ `VoiceStatusBar`, `AgentOrbStateBridge`, `VoiceActionDock` already read `AgentActivityController`
- ✅ Workbench panels already read `AgentActivityController`

### Actual Gaps
`AgentActivityController` currently does **not** handle:
- ✅ Missing: `assistant_final` completion logic
- ✅ Missing: `research_result` task completion
- ✅ Missing: `media_result` task completion
- ✅ Missing: `system_result` task completion/failure
- ✅ Missing: `confirmation_required` waiting state
- ✅ Missing: `confirmation_response` state clearing
- ✅ Missing: `error` task failure handling
- ✅ Missing: `turn_complete` cleanup logic

**Critical Gap:** Does not clear `_activeToolName`, `_activeTaskId`, or confirmation state on reconnect/disconnect.

---

## Design Decisions

### 1. Keep `SessionProvider` as Only Event Ingress Boundary
No changes to transport or validation ownership.

### 2. Keep `ChatProvider` as Transcript Owner
`ChatProvider` remains owner of:
- Transcript messages and rendering
- Assistant streaming merge
- Structured result bubbles
- Confirmation/system/media/research message rows

### 3. No New `EventLifecycleManager` in Phase 8
Defers complex event ordering, buffering, and reconciliation to Phase 8.5.

### 4. `AgentActivityController` for Activity State Only
`AgentActivityController` becomes canonical source for:
- Voice UI state
- Active task/tool display
- Workbench activity logs
- Task completion/failure/waiting state

Does NOT become full transcript or event-replay engine.

### 5. No `ChatProvider.agentState` Migration
Leave it intact for backward compatibility during Phase 8.

### 6. No New Voice-State Enum for Confirmation
Confirmation handled via overlay + workbench task state. Voice returns to `idle`, not `waiting`.

---

## Primary Ownership Model

| Component | Primary Responsibility |
|-----------|------------------------|
| **SessionProvider** | Event ingress, validation, normalized emission |
| **ChatProvider** | Transcript and chat artifact rendering |
| **AgentActivityController** | Voice/activity/task/log state |
| **OverlayController** | Transient overlays |
| **ConversationController** | Conversation snapshots and artifact selection |
| **WorkspaceController** | Layout/workbench selection |

Events can affect multiple surfaces, but each state domain has one primary owner.

---

## Implementation Plan

### Workstream 1 — Reconnect & Bootstrap Hygiene
**Goal:** Fix stale activity state before adding result handlers.

**File:** `lib/state/controllers/agent_activity_controller.dart`

**Required State:**
- `_activeConfirmationTraceId: String?`
- `_confirmationTaskIdsByTraceId: Map<String, String>`

**Event Behavior:**

| Event | Required Actions |
|-------|------------------|
| **session_disconnected** | - Clear `_activeToolName`<br>- Clear `_activeTaskId`<br>- Clear confirmation state<br>- Set `VoiceUiState.offline`<br>- Log warning |
| **session_reconnecting** | - Clear `_activeToolName`<br>- Clear `_activeTaskId`<br>- Clear confirmation state<br>- Set `VoiceUiState.reconnecting`<br>- Log warning |
| **session_connected** | - If not bootstrapping, set `idle`<br>- Log |
| **bootstrap_started** | - Set `VoiceUiState.bootstrapping`<br>- Log |
| **bootstrap_acknowledged** | - Clear bootstrap<br>- Set `idle`<br>- Log |
| **bootstrap_timeout** | - Clear bootstrap<br>- Set `idle`<br>- Log warning |

**Rule:** Reconnect/bootstrap cleanup must not depend on transcript state.

---

### Workstream 2 — Complete `AgentActivityController` Event Handling
**Goal:** Add missing result/completion handlers that drive activity cleanup and workbench state.

**File:** `lib/state/controllers/agent_activity_controller.dart`

**Required Helpers:**
- `_findTask(String taskId)`
- `_findOrCreateTask(String taskId, String name, DateTime eventTime)`
- `_completeTask(String taskId, {String? result, DateTime? eventTime})`
- `_failTask(String taskId, {String? result, DateTime? eventTime})`
- `_setTaskWaiting(String taskId, DateTime eventTime)`

**Task ID Rules:**
- If `taskId` is null/empty: **DO NOT** create task or use placeholder
- Task state updates must be **idempotent by real taskId**
- The plan forbids invented task IDs like `unknown_task`

**Event Handling Matrix:**

| Event | Log | Voice State | Task State | Active Task Cleared? |
|-------|-----|-------------|------------|------------------------|
| **assistant_final** | ✅ | thinking/toolRunning → idle | None | ❌ |
| **research_result** (matches active) | ✅ | unchanged | Complete active task | ✅ |
| **research_result** (historical) | ✅ | unchanged | Complete historical task only | ❌ |
| **media_result** (matches active) | ✅ | unchanged | Complete active task | ✅ |
| **media_result** (historical) | ✅ | unchanged | Complete historical task only | ❌ |
| **system_result** (success + matches) | ✅ | unchanged | Complete active task | ✅ |
| **system_result** (failure + matches) | ✅ | unchanged | Fail active task | ✅ |
| **system_result** (historical) | ✅ | unchanged | Complete/fail historical | ❌ |
| **confirmation_required** | ✅ | idle | waiting_input + set active | ✅ |
| **confirmation_response** (matches) | ✅ | unchanged | waiting → running | ❌ |
| **error** (matches active) | ✅ | idle | Fail active task | ✅ |
| **error** (no taskId) | ✅ | idle | None | ✅ |
| **turn_complete** | ✅ | idle (if not speaking) | None | ❌ |

**Delayed Result Rule:** If `research_result`, `media_result`, or `system_result` arrives for a historical task:
- Keep transcript behavior unchanged
- Complete/fail that historical task if valid taskId
- **DO NOT** reactivate or override current voice state unless event task matches current active task

---

### Workstream 3 — Verify Existing UI Surfaces
**Goal:** Don't rewrite surfaces already wired correctly. Confirm they reflect new controller state.

**Files to Verify:**
- `lib/widgets/layout/voice_status_bar.dart`
- `lib/widgets/layout/agent_orb_state_bridge.dart`
- `lib/widgets/layout/voice_action_dock.dart`
- `lib/widgets/features/workbench/`

**Required Outcome:**
- Confirm they reflect newly-complete controller state correctly
- Make only minimal fixes if specific surface fails

**Non-Goal:** Do not migrate transcript widgets or overlay ownership.

---

### Workstream 4 — Keep `ChatProvider` Stable
**Goal:** Avoid broad transcript changes during sync phase.

**File:** `lib/state/providers/chat_provider.dart`

**Rules:**
- ❌ No authority migration
- ❌ No removal of `agentState`
- ❌ No transcript ownership changes
- ❌ No assistant delta/final merge redesign

**Allowed Change:** Only minimal compatibility adjustments if concrete conflict observed during tests.

---

### Workstream 5 — Tests
**Goal:** Add only tests required by changed behavior.

**Required Test Updates:**

#### 1. `test/state/controllers/agent_activity_controller_test.dart`
Add tests for:
- `research_result` completes matching task and logs
- delayed `research_result` completes historical task without changing unrelated voice state
- `media_result` completes matching task
- `system_result` completes/fails matching task based on success
- `confirmation_required` sets task to `waiting_input` and voice to `idle`
- `confirmation_response` clears waiting state and confirmation tracking
- `error` fails task and clears active state
- `assistant_final` clears `thinking`/`toolRunning` → `idle`
- `session_disconnected` clears active tool/task/confirmation
- `session_reconnecting` clears active tool/task/confirmation and sets reconnecting
- `bootstrap_acknowledged` and `bootstrap_timeout` return to idle

#### 2. `test/widgets/layout/voice_status_bar_test.dart`
Add/update tests for:
- reconnecting state
- bootstrapping state
- idle after result completion
- idle after error cleanup

#### 3. `test/widgets/layout/agent_orb_state_bridge_test.dart`
Add/update tests for:
- reconnecting → initializing
- offline → muted
- idle after completion/error cleanup

#### 4. `test/widgets/features/workbench/`
Add/update only what controller changes affect:
- task list shows completed/failed/waiting_input
- logs include result/error/confirmation lifecycle messages

#### 5. `test/state/providers/session_provider_event_validation_test.dart`
Add tests only if needed for:
- parseable schema mismatch still reaches activity consumers safely
- invalid event still falls back without leaving stale UI state

**Not Required in Phase 8:**
- Large event-ordering matrix
- Reconnect replay tests
- Duplicate event reconciliation tests

---

## Manual Validation

Run these **3 scenarios** after implementation:

### Scenario 1 — Research Completion
1. Trigger research flow
2. Confirm transcript shows result
3. Confirm matching task completes in workbench
4. Confirm orb/status return to idle

### Scenario 2 — Confirmation Flow
1. Trigger confirmation-required action
2. Confirm overlay appears
3. Confirm task enters `waiting_input`
4. Confirm voice status is idle (not thinking)
5. Confirm response clears waiting state cleanly

### Scenario 3 — Reconnect During Active Flow
1. Start tool/research activity
2. Force disconnect/reconnect
3. Confirm active tool/task/confirmation clears
4. Confirm reconnect/offline states show correctly
5. Confirm delayed structured result doesn't reactivate stale activity state

---

## Validation Gate

Run after implementation:

```bash
cd agent-starter-flutter-main

flutter test \
  test/state/controllers/agent_activity_controller_test.dart \
  test/widgets/layout/voice_status_bar_test.dart \
  test/widgets/layout/agent_orb_state_bridge_test.dart \
  test/widgets/features/workbench/ \
  test/state/providers/session_provider_event_validation_test.dart
```

Optional backend safety check:

```bash
cd Agent
pytest tests/test_communication_events.py tests/test_agent_orchestrator.py -q
```

---

## Execution Order

Use this order exactly:

1. **Workstream 1** — reconnect/bootstrap cleanup
2. **Workstream 2** — missing activity handlers
3. **Workstream 5** — controller tests (parallel with Workstream 2)
4. **Workstream 3** — verify existing UI surfaces, minimal fixes only
5. **Workstream 4** — touch `ChatProvider` only if concrete conflict found
6. Run validation gate
7. Do 3 manual scenarios

**Why this order:**
- Lifecycle cleanup must be correct before result handlers are trustworthy
- Most UI surfaces are already wired and should not be churned early
- Tests should validate changed controller first, not drive wide rewrite

---

## Public API Changes

**No backend API changes.**
**No event schema changes.**
**No new Flutter public widget APIs.**

**Allowed internal changes:**
- New private fields/helpers in `AgentActivityController`
- Optional small compatibility change in `ChatProvider`
- No new `VoiceUiState` enum members by default

---

## Assumptions & Defaults

- `SessionProvider` remains only ingress/validation boundary
- `ChatProvider` remains transcript owner for all of Phase 8
- Delayed structured results should still be shown, not dropped
- Delayed results must not override unrelated current activity state
- Task state only created/updated when real `taskId` exists
- Confirmation waiting represented via overlay + workbench task state, not new voice UI enum
- Advanced event lifecycle management deferred to Phase 8.5

---

## Success Criteria

Phase 8 is complete when:

- [ ] `AgentActivityController` clears active tool/task/confirmation on reconnect
- [ ] `AgentActivityController` handles all listed result/completion events
- [ ] Workbench task list shows completed/failed/waiting states correctly
- [ ] Voice status bar shows reconnecting/bootstrapping/idle transitions
- [ ] Orb reflects correct state transitions
- [ ] Research completion updates workbench and returns voice to idle
- [ ] Confirmation flow works end-to-end: waiting → response → cleared
- [ ] Scenario 1 (research) passes manual validation
- [ ] Scenario 2 (confirmation) passes manual validation
- [ ] Scenario 3 (reconnect) passes manual validation
- [ ] Flutter validation gate passes with 0 failures
- [ ] No breaking changes to `ChatProvider` public API

---

## Related Files

**Core Files:**
- `lib/state/controllers/agent_activity_controller.dart`
- `lib/state/providers/session_provider.dart`
- `lib/state/providers/chat_provider.dart`
- `lib/core/events/agent_event_validator.dart`

**UI Surfaces:**
- `lib/widgets/layout/voice_status_bar.dart`
- `lib/widgets/layout/agent_orb_state_bridge.dart`
- `lib/widgets/layout/voice_action_dock.dart`
- `lib/widgets/features/workbench/`

**Tests:**
- `test/state/controllers/agent_activity_controller_test.dart`
- `test/widgets/layout/voice_status_bar_test.dart`
- `test/widgets/layout/agent_orb_state_bridge_test.dart`
- `test/widgets/features/workbench/`

---

## Next Steps

1. Review this plan with stakeholders
2. Create implementation branch
3. Execute Workstream 1 (reconnect/bootstrap cleanup)
4. Execute Workstream 2 (event handlers) + Workstream 5 (tests)
5. Verify UI surfaces (Workstream 3)
6. Run validation gate
7. Execute manual scenarios
8. Merge on validation gate pass

---

*Plan Version: 1.0*
*Last Updated: 2026-03-20*
*Owner: Development Team*
*Next Review: Phase 8 Completion*
