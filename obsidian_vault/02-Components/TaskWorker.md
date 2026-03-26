# TaskWorker

## Responsibility
Background loop that polls TaskStore for RUNNING tasks and executes them.

## Inputs
- Task definitions from TaskStore
- Tool configurations

## Outputs
- Task execution results
- Status updates (COMPLETED/FAILED)
- TaskStore updates

## Internal Logic
1. Poll TaskStore every N seconds
2. Look for tasks with status=RUNNING
3. Execute task via ToolManager
4. Update status in TaskStore
5. Continue until all tasks complete

## Dependencies
- [[TaskStore]]
- [[ToolManager]]

## Related
- [[Task Worker System]]
- [[PlanningEngine]]
