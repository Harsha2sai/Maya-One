# SmartLLM

## Responsibility
LLM wrapper with provider abstraction. Handles tool schemas and response parsing. Manages role switching for different agent modes.

## Inputs
- User message
- Context (from ContextBuilder)
- Tools list (if applicable)
- Role specification (CHAT/TOOL_ACTION/PLANNER/WORKER)

## Outputs
- LLM response
- Parsed tool calls (if any)
- Formatted answer

## Internal Logic
1. Receive role specification from ExecutionRouter
2. Build context within token budget
3. Format tools according to provider requirements
4. Call provider (Groq, OpenAI, etc.)
5. Parse response
6. Extract tool calls if present
7. Return to caller

## Known Issues
- Tool-call schema mismatch between SmartLLM ↔ LiveKit ↔ WorkerToolParser
- Schema patch uses `strict_tool_schema = False` as compatibility hack
- Requires proper alignment across adapters

## Dependencies
- [[Role-Based LLM System]]
- [[ToolManager]]
- [[ProviderFactory]]

## Related
- [[RoleLLM]]
- [[ExecutionRouter]]
