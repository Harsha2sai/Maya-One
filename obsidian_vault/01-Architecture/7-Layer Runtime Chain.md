# 7-Layer Runtime Chain

## Purpose
Defines the strict layered architecture that all runtime execution must follow. Never bypass layers.

## Components
**Layer 1: Lifecycle Layer** (`core/runtime/lifecycle.py`)
- Responsible for booting modes: CONSOLE, WORKER, VOICE
- LifecycleManager is the single entrypoint
- NOTHING bypasses LifecycleManager

**Layer 2: Console Harness** (`core/runtime/console_harness.py`)
- Contains ONLY: `run_console_agent(entrypoint_fnc)`
- Interactive loop only, no agent creation
- Forwards text → entrypoint only

**Layer 3: Entrypoint Layer** (`agent.py`)
- Contract: `async def entrypoint(user_message: str)`
- Routes message to global agent components
- No runtime boot logic (Lifecycle already warmed global resources)

**Layer 4: Global Agent Container** (`core/runtime/global_agent.py`)
- Initializes shared resources ONCE at boot:
  - HybridMemoryManager
  - SQLiteTaskStore
  - ProviderFactory (LLM/STT/TTS)
  - ToolManager

**Layer 5: Orchestrator Layer** (`core/orchestrator/agent_orchestrator.py`)
- Main brain: `AgentOrchestrator.handle_message()`
- Handles planning, task creation, delegation

**Layer 6: Task + Worker Layer** (`core/tasks/`)
- Flow: PlanningEngine → TaskStore → TaskWorker → Tool execution

**Layer 7: Tools Layer** (`core/tools/`)
- Tools registered once and passed to LLM

## Data Flow
```
LifecycleManager
 ↓
ConsoleHarness
 ↓
Entrypoint (agent.py)
 ↓
GlobalAgentContainer
 ↓
AgentOrchestrator
 ↓
Planner / Workers / Tools
```

## Dependencies
- [[LifecycleManager]]
- [[ConsoleHarness]]
- [[GlobalAgentContainer]]
- [[AgentOrchestrator]]

## Related
- [[Single-Brain Pattern]]
- [[Phase Architecture]]
- [[Task Worker System]]
