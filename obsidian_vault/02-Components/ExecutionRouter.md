# ExecutionRouter

## Responsibility
Classifies user intent into categories before expensive LLM generation to save latency.

## Inputs
- User message

## Outputs
- Intent classification:
  - CONVERSATION
  - TOOL_ACTION
  - MEMORY_QUERY
  - CLARIFICATION
  - TASK_REQUEST

## Internal Logic
1. Analyze message pattern and keywords
2. Classify into one of 5 categories
3. Route accordingly:
   - CONVERSATION → Chat LLM (no tools, no memory)
   - TOOL_ACTION → Tool LLM (with tools only)
   - MEMORY_QUERY → Planner LLM + Memory retrieval
   - CLARIFICATION → Request more info
   - TASK_REQUEST → PlanningEngine

## Dependencies
- [[Intent-First Routing]]
- [[AgentOrchestrator]]

## Related
- [[Role-Based LLM System]]
- [[SmartLLM]]
