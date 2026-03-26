# ToolManager

## Responsibility
Central registry and execution coordinator for all tool operations across the system.

## Core Functions

### 1. MCP Integration (`initialize_agent_with_mcp`)
- Configures n8n MCP servers via SSE
- Combines remote MCP tools with local tools
- Registers tools with `Agent._tools` before deduplication
- Fixes schema mismatches between SmartLLM ↔ LiveKit ↔ WorkerToolParser

### 2. Tool Discovery (`load_all_tools`)
- Loads tools from MCP servers
- Combines with local Python tools
- Extracts metadata for registry
- Builds canonical tool map (name → tool)
- Registers with WorkerToolRegistry and ExecutionRouter

### 3. Metadata Extraction (`extract_metadata`)
- Extracts: name, description, inputSchema from tools
- Handles both LiveKit FunctionTool and raw python functions
- Creates structured metadata for Tool Registry

### 4. Execution Router Integration (`_configure_router`)
Registers tool executor with O(1) lookup:
```python
router.set_tool_executor(tool_executor)
```

Execution path:
1. **Gate Check** → ExecutionGate.check_access()
2. **Audit Entry** → AuditLogger.log_attempt()
3. **Trace Context** → trace_id, session_id, user_id
4. **Execute** → Strategy dispatch:
   - LiveKit FunctionTool (wrapped)
   - LiveKit FunctionTool.call
   - Raw Callable
5. **Audit Result** → AuditLogger.log_result()
6. **Event Publish** → publish_tool_execution() to room

## Tool Execution Governance

### Risk & Access Control
- **ExecutionGate** checks user roles (GUEST, USER, ADMIN, DEVELOPER)
- **AuditLogger** creates traceable execution records
- **Probe Engine** instruments execution with metrics
- **Chaos Config** simulates failures for resilience testing

### Mock Context Injection
```python
class MockJobContext: def __init__(self, uid): self.user_id = uid
class SimpleContext: def __init__(self, uid): self.job_context = MockJobContext(uid)
```

Context injected for persistence tools like memory storage.

## Tool Strategy Selection
- **Detection**: Check for `.__wrapped__` (LiveKit tools)
- **Direct Call**: Use `.call(params, context)` for LiveKit FunctionTool
- **Callable**: Inspect signature with `inspect.signature()`
- **Fallback**: Use raw callable with context if accepted

## Tool Execution Events
Published to LiveKit room for Flutter UI:
```json
{
  "type": "tool_execution",
  "status": "started|finished",
  "tool_name": "web_search",
  "params": {...},
  "result": "...",
  "task_id": "task-123",
  "turn_id": "turn-456"
}
```

## Integration Points
- **GlobalAgentContainer** → ToolManager initializes at boot
- **WorkerToolRegistry** → Receives canonical tool map for O(1) lookup
- **ExecutionRouter** → Receives tool executor function
- **AgentOrchestrator** → Agent._tools comes from ToolManager
- **Audit System** → All executions logged
- **Chaos Testing** → Controlled failure injection
- **Flutter Bridge** → Event publishing for UI

## Configuration
```bash
# MCP Server (optional)
export N8N_MCP_SERVER_URL="http://localhost:3000/api/mcp"
```

## Files
- `Agent/core/tools/tool_manager.py`
- `Agent/core/registry/tool_registry.py`
- `Agent/core/routing/router.py`
- Related: `Agent/core/governance/gate.py`, `Agent/core/governance/audit.py`

## Related
- [[ExecutionRouter]]
- [[GlobalAgentContainer]]
- [[WorkerToolRegistry]]
- [[Task Worker System]]
- [[AgentOrchestrator]]
