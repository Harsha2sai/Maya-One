# GlobalAgentContainer

## Responsibility
Singleton that initializes shared resources ONCE at boot to prevent duplicate runtimes and dual-brain boot loops.

## Inputs
- Environment variables (via `config/settings.py`)
- Provider configurations
- Tool definitions

## Outputs
- Pre-warmed orchestrator instance
- Shared memory manager
- Task store
- Provider factory
- Tool manager

## Internal Logic
Resources created at boot:
1. **HybridMemoryManager** - Vector + FTS5 keyword search
2. **SQLiteTaskStore** - Task persistence
3. **ProviderFactory** - LLM/STT/TTS providers
4. **ToolManager** - Tool registry
5. **Agent Registry**

All resources created ONCE and shared across all message handling. Never recreated per message.

## Dependencies
- [[7-Layer Runtime Chain]]
- [[LifecycleManager]] (called at boot)

## Known Issues
- Previously: Console handler created new orchestrator instances (FIXED by using GlobalAgentContainer.get_orchestrator())
- Tool-call schema mismatch between SmartLLM ↔ LiveKit ↔ WorkerToolParser (ongoing)

## Related
- [[Single-Brain Pattern]]
- [[AgentOrchestrator]]
