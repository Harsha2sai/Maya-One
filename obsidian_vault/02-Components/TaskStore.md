# TaskStore

## Responsibility
SQLite-based persistent storage for tasks. Enables crash recovery and status tracking.

## Inputs
- Task definitions from PlanningEngine
- Status updates from TaskWorker

## Outputs
- Task lists by status
- Individual task details
- PERSISTENT storage across sessions

## Internal Logic
Runs in WAL mode for high concurrency.
Stores task state transitions:
PENDING → RUNNING → COMPLETED/FAILED

## Dependencies
- [[PlanningEngine]] (creates tasks)
- [[TaskWorker]] (executes and updates)

## Related
- [[Task Worker System]]
- [[PlanningEngine]]
- [[TaskWorker]]
