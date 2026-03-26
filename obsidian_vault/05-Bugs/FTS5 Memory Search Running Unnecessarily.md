# Bug: FTS5 Memory Search Running Unnecessarily

## Description
Memory search triggers for trivial messages ("hi", "hhhii", etc.) causing unnecessary DB calls, embeddings, and planner noise.

## Root Cause
- Small-talk detection logic not comprehensive
- Memory search runs before intent classification
- No bypass for trivial patterns

## Affected Components
- HybridMemoryManager
- Intent-First Routing (`core/intelligence/rag_engine.py`)
- ContextBuilder (`core/context/context_builder.py`)
- PlanningEngine (gets unnecessary planning calls)

## Fix Applied
Partial fix implemented in Phase 6, but detection needs improvement.

## Status
🟡 IMPORTANT - Ongoing investigation

## Related
- [[Hybrid Memory System]]
- [[Intent-First Routing]]
- [[Small-Talk Bypass]]
- [[PlanningEngine]]
