# Task Worker System

## Purpose
Provides persistent, recoverable task execution through a planning → storage → execution pipeline.

## Components
**PlanningEngine** (`core/tasks/PlanningEngine`)
- Breaks complex tasks into bite-sized tasks (2-5 min each)
- Each task has:
  - Exact file paths
  - Complete code specifications
  - Verification steps

**TaskStore** (SQLite database)
- Persists tasks before execution
- Enables crash recovery
- Stores task state (PENDING, RUNNING, COMPLETED, FAILED)

**TaskWorker**
- Background loop polling TaskStore
- Executes RUNNING tasks
- Reports completion/failure

## Data Flow
```
PlanningEngine → TaskStore (persist) → TaskWorker (poll) → Tool execution
```

## Internal Logic
1. Complex request → AgentOrchestrator
2. AgentOrchestrator → PlanningEngine
3. PlanningEngine → breaks into atomic tasks
4. Tasks → TaskStore (SQLite)
5. TaskWorker (background) → polls for RUNNING
6. Execute task → Tools
7. Update status → TaskStore
8. Continue until complete

## Dependencies
- [[AgentOrchestrator]]
- [[PlanningEngine]]
- [[ToolManager]]

## Related
- [[7-Layer Runtime Chain]]
- [[Subagent-Driven Development]]
