# AgentOrchestrator

## Responsibility
Central decision hub. Main brain of the system. Receives messages and orchestrates all agent operations.

## Inputs
- User message from entrypoint
- Pre-warmed global resources from GlobalAgentContainer

## Outputs
- Planning requests
- Task creation
- Worker delegation
- Final responses

## Internal Logic
1. Receive message via `handle_message()`
2. Route to appropriate handler based on intent
3. Invoke planning if complex task
4. Create tasks via TaskStore
5. Delegate to workers
6. Collect results
7. Formulate response

## Dependencies
- [[GlobalAgentContainer]]
- [[PlanningEngine]]
- [[TaskStore]]
- [[ToolManager]]

## Known Issues
- Context token bloat (addressed in Phase 6)

## Related
- [[7-Layer Runtime Chain]]
- [[Intent-First Routing]]
- [[Task Worker System]]
