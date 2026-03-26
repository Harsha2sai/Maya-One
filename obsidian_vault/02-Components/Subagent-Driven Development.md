# Subagent-Driven Development

## Purpose
Pattern for spawning specialized sub-agents to handle domain-specific tasks, enabling parallel execution and modularity.

## Architecture
Subagent-driven development is not a single component but a meta-pattern that spans the architecture. It manifests through:

### 1. Task → Subagent Mapping
```
User Request → AgentOrchestrator → PlanningEngine → TaskStore → TaskWorker (Dispatcher) → Specialist Workers
```

### 2. Specialist Worker Types
Each worker acts as a sub-agent with domain-specific expertise:
- **ResearchWorker** → Web search, data extraction
- **CodeWorker** → Code analysis, syntax validation
- **MediaWorker** → Audio/image processing
- **MemoryWorker** → Vector/FTS5 retrieval
- **ToolWorker** → Generic tool execution
- **AnalysisWorker** → Data interpretation

### 3. Execution Flow
1. **TaskWorker** fetches RUNNING tasks from TaskStore
2. StepController dispatches to registered specialist worker
3. Worker executes using dedicated ToolManager instance
4. Result stored in TaskStore
5. TaskWorker continues until task completion

## Developer API
Specialist workers inherit from base patterns:
```python
class SpecialistWorker:
    def can_handle(self, step: TaskStep) -> bool:
        """Check if worker supports this step type"""

    async def execute(self, step: TaskStep, context: ExecutionContext) -> StepResult:
        """Execute step with domain-specific logic"""
```

## Key Features
- **Isolation**: Failures in one sub-agent don't cascade
- **Parallelism**: Multiple tasks run on different workers
- **Persistence**: Task state survives crashes via TaskStore
- **Specialization**: Workers optimize for their domain
- **Governance**: ExecutionGate & AuditLogger track all sub-agents

## Integration Points
- **PlanningEngine** → Decomposes tasks into sub-agent steps
- **WorkerRegistry** → Maps step types to specialist workers
- **ExecutionEvaluator** → Grades sub-agent performance
- **ToolManager** → Each sub-agent gets subset of tools
- **StepController** → Orchestrates sub-agent dispatch

## Example: Research Task
```
User: "Research Claude features"
→ AgentOrchestrator → PlanningEngine
  → Step 1: "Search web for Claude features" → ResearchWorker
  → Step 2: "Analyze search results" → AnalysisWorker
  → Step 3: "Synthesize answer" → TaskWorker (final)
```

## Related
- [[Task Worker System]]
- [[PlanningEngine]]
- [[TaskWorker]]
- [[WorkerRegistry]]
- [[ExecutionEvaluator]]
- [[StepController]]
