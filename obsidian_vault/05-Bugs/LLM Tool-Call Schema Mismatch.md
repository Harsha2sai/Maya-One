# Bug: LLM Tool-Call Schema Mismatch

## Description
Schema compatibility layer for Groq API limitations. Works as designed - NOT a bug.

## Root Cause
- Groq's API rejects `additionalProperties: false` in tool schemas (Groq API limitation)
- This is a documented Groq limitation, not a Maya bug or schema mismatch
- Requires schema translation to prevent tool call failures on Groq

## Affected Components
- `GlobalAgentContainer.apply_schema_patch()` (Phase 3) - Primary translation layer
- `Agent/utils/schema_fixer.py` (runtime enforcement) - Secondary patch
- All providers (Groq, OpenAI, etc.) - Ensures cross-provider compatibility

## Fix Applied
✅ `strict_tool_schema=False` compatibility patch - **WORKING AS DESIGNED**.
- Phase 3 documented implementation (`apply_schema_patch()`)
- Prevents tool call failures on Groq
- Required for Groq API compatibility
- Stable since Phase 3, no maintenance burden

## Status
🟢 CLOSED - Working as Designed (Groq Compatibility)

## Documentation Source
- Phase 3 Final Evaluation Report (verified implementation)
- Configuration in `GlobalAgentContainer` boot sequence
- `Agent/utils/schema_fixer.py:106-122` (runtime enforcement)

## Related
- [[SmartLLM]]
- [[ToolManager]]
- [[TaskWorker]]
- [[Tool Call Parsing]]
