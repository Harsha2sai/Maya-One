# Decision: Console Handler Using Old Orchestrator API

## Context
- Console handler was written for old architecture where Orchestrator was created per-message
- GlobalAgentContainer now creates Orchestrator once at boot
- Console handler was creating new orchestrator instances, causing dual-brain issues

## Decision
**Fix Applied:**
1. Added `ConsoleOrchestrator` to `GlobalAgentContainer._orchestrator` (initialized once at boot)
2. Added `get_orchestrator()` classmethod to container
3. Updated `_handle_console_message()` to use `GlobalAgentContainer.get_orchestrator()` instead of creating new instance

## Reasoning
- Console must align with [[Single-Brain Pattern]]
- Prevent duplicate runtimes
- Ensure all console messages use pre-warmed orchestrator
- Maintain 7-layer runtime chain integrity

## Tradeoffs
**Benefits:**
- ✅ Fixes dual-brain boot loop
- ✅ Console aligns with architecture
- ✅ Faster console responses (pre-warmed)

**Costs:**
- None - this fixes a design violation

## Impacted Components
- `GlobalAgentContainer` (`core/runtime/global_agent.py`) - Added orchestrator to container
- `agent.py` - Uses container's orchestrator instead of creating new one
- [[Console Harness]] (uses GlobalAgentContainer)

## Related
- [[7-Layer Runtime Chain]]
- [[Single-Brain Pattern]]
- [[GlobalAgentContainer]]
