# Phase Architecture

## Purpose
8-phase architecture rollout controlling system evolution. Current phase controlled by MAYA_ARCH_PHASE environment variable.

## Components

### Phase 1: Global Resources & Provider Initialization ✓
- Completed: Global container setup and provider initialization

### Phase 2: Orchestration & Single-Brain Execution ✓
- Completed: Single orchestrator instance management

### Phase 3: Tool Pipeline Integration ✓
- Completed Feb 22
- Tool registration and execution

### Phase 4: Intent, Planning & Worker Execution ✓
- Completed Feb 28, all tests passed
- Intent classification and task execution

### Phase 5: Voice Pipeline (Audio Session Management) ✓
- Verified Feb 28
- Audio handling and session management
- Status: Stable, TTS priority queue added in Phase 7

### Phase 6: Memory System & Context Integrity ✓
- Completed Mar 4, 2026
- Context gating: Removed inline context fallback, proper tool gating
- Token budget reduced to < 2000 for efficiency
- Files: `core/context/context_builder.py`, `core/tools/tool_manager.py`, `core/context/final_context_guard.py`
- Component: [[ContextBuilder]] - Full documentation available

### Phase 7: Provider Resilience & Chaos Recovery ✓
- Completed Mar 7, 2026
- Trace propagation & TTS priority
- Planner repair with proper trace propagation
- TTS priority queue for voice stability
- Worker execution traceability
- Provider health monitoring integration
- Files: `core/tasks/planning_engine.py`, `core/audio/audio_session_manager.py`, `core/providers/resilient_tts.py`
- Decisions: [[Trace Propagation]], [[TTS Priority Queue]]

### Phase 8: Frontend State Synchronization ✓
- Completed: March 21, 2026
- Workstreams 1-4: Reconnect/bootstrap, event handlers, UI verification, ChatProvider stability
- Live event visibility: agent_thinking, research_pending, tool_execution, research_result, agent_speaking, turn_complete
- Chat-thread isolation to prevent result leakage
- Flutter UI surfaces stable, no new state enum members needed
- Files: `agent-starter-flutter-main/lib/core/events/`, `Agent/core/runtime/event_manager.py`

## Current Status (March 16, 2026)
- **Phase 8 Starter**: "MEGA Era" advanced query interpretation
- **Test Status**: All tests passed (Phase 7 complete)
- **Validated Suites**:
  - `test_planning_engine.py`
  - `test_worker_dispatch.py`
  - `test_agent_orchestrator.py`
  - `test_phase6_context_gating.py`
  - `test_phase7_trace_propagation.py`
  - `test_tts_priority_queue.py`

### Phase 9: Multi-Agent Handoff & Specialization ✓
- Completed: March 22, 2026
- **Phase 9A**: Internal handoff contracts for research, system_operator, planner agents
- **Phase 9B**: Media agent specialization (play, pause, next, volume controls)
- **Phase 9C**: Worker prompt authority architecture with overlays
- **Phase 9D**: Scheduling agent specialization (reminders, alarms, calendar events)
- **Key Components**:
  - [[HandoffManager]] with depth/parent guards
  - [[AgentHandoffRequest]]/[[AgentHandoffResult]] contracts
  - Worker prompt base + overlays for type-specific behavior
  - Host capability profile for resource-aware planning
  - Specialist agents: media, scheduling (with deterministic fast-paths preserved)
- **Certification**: 15-turn mixed session validated all handoff lifecycles
- **Test Coverage**: 266+ tests passing, targeted certification bundles green
- Files: `Agent/core/agents/handoff_manager.py`, `Agent/core/prompts/`, `Agent/core/agents/scheduling_agent_handler.py`, `Agent/core/agents/media_agent_handler.py`

## Related
- [[7-Layer Runtime Chain]]
- [[Context Gating and Tool Safety]]
- [[Trace Propagation]]
- [[TTS Priority Queue]]
- [[HandoffManager]]
- [[Subagent-Driven Development]]
- [[ExecutionManager]]
- [[ToolManager]]
- [[ContextBuilder]]
