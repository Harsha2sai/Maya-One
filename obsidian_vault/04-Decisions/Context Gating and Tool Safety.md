# Decision: Context Gating and Tool Safety

## Context
- Context token usage at 2424 tokens with 3.8s first token latency
- System suffering from context bloat
- Inline context fallback causing bloated contexts
- Tools being misused in inappropriate scenarios
- Context token budget at 12000 tokens (excessive)

## Decision
**Phase 6 Implementation:**
1. Removed inline context fallback
2. Enforce proper tool gating
3. Reduce context token budget to < 2000 tokens
4. Prevent misuse of recall tool in inappropriate scenarios

## Reasoning
- Ensure clean, minimal context for each LLM call
- Prevent context contamination between different LLM roles
- Improve token efficiency
- Reduce response time
- Prevent tool abuse

## Tradeoffs
**Benefits:**
- ✅ Cleaner, more focused context
- ✅ Better token efficiency
- ✅ Faster response times
- ✅ Reduced costs
- ✅ Better role separation

**Costs:**
- ⚠️ Some queries may need clearer context
- ⚠️ May need refinement of tool gating rules
- ⚠️ System prompts need to be more precise

## Impacted Components
- [[Context Builder]] (`core/context/context_builder.py`)
- [[ToolManager]] (`core/tools/tool_manager.py`)
- [[ContextGuard]] (`core/context/final_context_guard.py`)
- [[SmartLLM]] (tool access patterns)
- [[ExecutionRouter]] (small-talk bypass)

## Related
- [[Memory Context Guard]]
- [[Small-Talk Bypass]]
- [[Hybrid Memory System]]
