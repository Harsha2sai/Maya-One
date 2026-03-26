# PlanningEngine

## Responsibility
Breaks complex tasks into bite-sized atomic tasks (2-5 minutes each) with exact specifications.

## Inputs
- Complex user request
- Current context
- Available tools

## Outputs
- List of atomic tasks
- Each task contains:
  - Exact file paths
  - Complete code specifications
  - Verification steps
  - Dependencies

## Internal Logic
1. Analyze complex request
2. Identify required steps
3. Decompose into atomic tasks
4. Ensure each task is 2-5 minutes
5. Add verification criteria
6. Store in TaskStore

## Dependencies
- [[AgentOrchestrator]]
- [[TaskStore]]
- [[ToolManager]]

## Related
- [[Task Worker System]]
- [[TaskStore]]
- [[TaskWorker]]
