# Single-Brain Pattern

## Purpose
Prevents duplicate runtimes and dual-brain boot loops by centralizing shared resource management in a singleton.

## Components
**GlobalAgentContainer** (`core/runtime/global_agent.py`)
- Singleton that initializes shared resources ONCE at boot
- Resources initialized:
  - HybridMemoryManager
  - SQLiteTaskStore
  - ProviderFactory (LLM/STT/TTS providers)
  - ToolManager
  - Agent Registry

**Key principle**: These resources must NEVER be recreated per message.

## Internal Logic
```python
# Correct usage
container = GlobalAgentContainer.get_orchestrator()
# Uses pre-warmed orchestrator instance

# WRONG - creates duplicate runtime
orchestrator = AgentOrchestrator(...)  # Creates new instance
```

## Data Flow
1. LifecycleManager boot → GlobalAgentContainer initialized
2. GlobalAgentContainer → creates all shared resources
3. Entrypoint receives message → accesses GlobalAgentContainer
4. Container provides pre-warmed instances to all components
5. No component creates its own runtime instances

## Dependencies
- [[7-Layer Runtime Chain]]
- [[LifecycleManager]]

## Known Issues
- Console handler previously created new orchestrator instances (FIXED)
- Tool-call schema mismatch between SmartLLM ↔ LiveKit ↔ WorkerToolParser (ongoing)

## Related
- [[AgentOrchestrator]]
- [[LifecycleManager]]
