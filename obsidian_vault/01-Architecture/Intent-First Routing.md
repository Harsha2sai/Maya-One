# Intent-First Routing

## Purpose
Classifies user intent BEFORE expensive LLM generation to save latency by bypassing heavyweight LLM for deterministic operations.

## Components
**ExecutionRouter**
- Classifies intent into categories:
  - CONVERSATION: General chat
  - TOOL_ACTION: Tool execution needed
  - MEMORY_QUERY: Memory retrieval required
  - CLARIFICATION: Needs more information
  - TASK_REQUEST: Complex task creation

## Internal Logic
1. Analyze user message pattern
2. Classify into intent category
3. Route to appropriate handler:
   - CONVERSATION → CHAT RoleLLM (no tools, no memory)
   - TOOL_ACTION → TOOL_ACTION RoleLLM (with tools)
   - MEMORY_QUERY → PLANNER RoleLLM + Memory retrieval
   - CLARIFICATION → Request more info from user
   - TASK_REQUEST → PlanningEngine for task creation

## Benefits
- Saves ~3.8s latency on first token
- Reduces unnecessary memory searches
- Prevents context bloat
- Improves response accuracy

## Dependencies
- [[Role-Based LLM System]]
- [[AgentOrchestrator]]

## Related
- [[Execution Router]]
- [[Context Builder]]
