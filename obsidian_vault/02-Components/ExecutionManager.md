# Execution Manager

## Purpose
Layer that coordinates the execution of tasks and steps after routing and planning.

**Note**: Not a single component. ExecutionManager is an architectural layer comprising:
- **TaskWorker** → Task dispatch and lifecycle management
- **StepController** → Step orchestration and execution flow
- **StepExecutor** → Individual step execution engine
- **ExecutionEvaluator** → Performance and safety evaluation

## Execution Flow

### 1. Task → Step Flow
```
PlanningEngine → TaskStore (persist) → TaskWorker (poll) → StepController → StepExecutor → Tool
					  ↑
					  │
				ExecutionEvaluator (evaluates outcomes)
```

### 2. TaskWorker Responsibilities
- Polls TaskStore for RUNNING tasks
- Maintains task lifecycle state
- Dispatches steps to StepController
- Handles failure and retry logic
- Publishes events to LiveKit room

### 3. StepController Responsibilities
```python
class StepController:
    - Determines execution order
    - Validates step inputs
    - Invokes StepExecutor
    - Handles continue/break logic
    - Evaluates execution results
```

**Key methods**:
- `execute_step(step: TaskStep, context: ExecutionContext) -> StepResult`
- `evaluate_completion(result: StepResult) -> Action`

### 4. StepExecutor Responsibilities
**Primitive action layer**:
- Tool execution
- Parameter validation
- Result parsing
- Error handling

**Execution strategies**:
- LiveKit FunctionTool (wrapped): `__wrapped__(context, **params)`
- LiveKit FunctionTool.call: `call(params, context)`
- Raw Callable: Direct invocation with signature inspection

### 5. ExecutionEvaluator Responsibilities
**Safety and quality assessment**:
- Valid return types
- No disallowed payloads
- Performance thresholds
- Error patterns (e.g., infinite loops, duplicate tool calls)
- Task completion confidence

**Failure modes**:
- `retryable` → Re-execute step
- `fatal` → Fail task
- `needs_fallback` → Escalate to Maya

## Execution Governance

### ExecutionGate
**Declarative tool access control**:
```python
ExecutionGate.check_access(tool_name, user_role):
    - Blocks disallowed tools
    - Returns denial reason
    - Logs to AuditLogger
```

**User roles**:
- GUEST: Restricted toolset
- USER: Standard toolset
- ADMIN: All tools except dangerous
- DEVELOPER: Dangerous tools allowed with confirmation

### AuditLogger
**Traceable execution records**:
```json
{
  "trace_id": "trace-123",
  "tool_name": "web_search",
  "user_role": "USER",
  "params": {"query": "..."},
  "latency_ms": 1200,
  "success": true
}
```

### Probe Engine
**Runtime instrumentation**:
```python
@probe_tool_execution
async def tool_executor(...) -> str:
    # Auto-instrumented metrics:
    # - execution_count
    # - average_latency
    # - failure_rate
    # - tool_usage_histogram
```

### Chaos Configuration
**Resilience testing**:
```python
chaos_config = {
    "enabled": True,
    "tool_failure_rate": 0.05,  # 5% failure rate
}
```
**Use**: Simulate failures to verify worker recovery

## Execution Events

### Lifecycle Events
Published to LiveKit room for Flutter UI:
```json
{
  "type": "tool_execution",
  "status": "started|finished",
  "tool_name": "weather",
  "params": {"location": "London"},
  "result": "Rainy, 15°C",
  "task_id": "task-uuid",
  "turn_id": "turn-uuid",
  "conversation_id": "conv-uuid"
}
```

### Error Events
```json
{
  "type": "tool_execution",
  "status": "error",
  "tool_name": "shell_command",
  "error": "Command not found: npm"
}
```

## Execution Context

### Thread-Local Context
```python
execution_context = {
    "user_id": "user-123",
    "turn_id": "turn-456",
    "task_id": "task-789",
    "trace_id": "trace-abc",
    "conversation_id": "conv-def",
}
```
**Use**: Trace execution across async boundaries

### Mock Context Injection
For persistence tools requiring user_id:
```python
class MockJobContext: def __init__(self, uid): self.user_id = uid
class SimpleContext: def __init__(self, uid): self.job_context = MockJobContext(uid)
```

## Execution Patterns

### Pattern 1: Simple Tool Call
```
User: "What's the weather?"
→ ExecutionRouter: TOOL_ACTION
→ ToolManager: web_search("weather")
→ StepExecutor: Executes tool
→ StepController: Evaluates result
→ Done
```

### Pattern 2: Multi-Step Task
```
User: "Research Claude features and summarize"
→ PlanningEngine: Creates 3 steps
→ Step 1: web_search("Claude features") → ResearchWorker
→ Step 2: analyze_results() → AnalysisWorker
→ Step 3: synthesize() → TaskWorker
→ TaskWorker: Marks task_complete
```
**Retry logic**: If Step 2 fails, retry up to 3 times

### Pattern 3: Background Task
```
User: "Research AI trends overnight"
→ PlanningEngine: background task with 50 steps
→ TaskWorker: Continues polling every 2 seconds
→ Flutter UI: Shows "Research in progress..."
→ Final: Publishes results when complete
```

## Error Handling

### Retry Strategy
```python
retry_count = step.metadata.get('retry_count', 0)
if retry_count < 3 and error.is_retryable():
    await asyncio.sleep(2**retry_count)  # Exponential backoff
    retry_count += 1
    requeue_step(step, retry_count)
else:
    fail_task(task, error)
```

### Timeout Protection
```python
STEP_TIMEOUT_SECONDS = 120  # 2 minutes per step
STEP_MAX_RETRIES = 3
```

### Stuck Task Detection
```python
STUCK_TASK_THRESHOLD_SECONDS = 600  # 10 minutes
if task.running_time > threshold:
    mark_task_failed(task, "stuck_task_detected")
```

## Performance Monitoring

### Key Metrics
- **Average step latency**: 800ms
- **Task completion rate**: 94%
- **Retry rate**: 8%
- **Tool execution rate**: 12 tools/task average
- **Peak throughput**: 5 concurrent tasks

### Bottlenecks
- **Tool cold start**: 200-500ms per tool
- **Memory retrieval**: 150-300ms per query
- **LLM generation**: 1.2-3.8s per call

## Integration Points
- **TaskWorker** → Polled by GlobalAgentContainer
- **StepController** → Consumed by TaskWorker
- **StepExecutor** → Uses ToolManager
- **ExecutionEvaluator** → Validates StepController decisions
- **AgentOrchestrator** → Initiates task creation
- **Flutter Bridge** → Receives execution events

## Files
```
Agent/core/tasks/
├── task_worker.py       # Dispatcher
├── step_controller.py   # Orchestrator
├── step_executor.py    # Basic executor
├── execution_evaluator.py  # Safety/quality evaluator
├── workers/
│   ├── base.py
│   ├── research_worker.py
│   ├── code_worker.py
│   ├── media_worker.py
│   ├── memory_worker.py
│   └── tool_worker.py
```

## Related
- [[ExecutionRouter]] (intent classification)
- [[Task Worker System]]
- [[ToolManager]] (tool execution)
- [[TaskOrchestrator]]
- [[PlanningEngine]]
