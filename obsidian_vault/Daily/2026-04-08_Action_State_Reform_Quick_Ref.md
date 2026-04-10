# Phase 28.5 Action State Reform - Quick Reference

**Created:** April 8, 2026
**Full Plan:** [[Phase_28_5_Action_State_Reform_Plan]]

## The Problem (Why This Matters)

Recent failures like "also Instagram" not working aren't parsing bugs - they're symptoms of the **"Agentic Chasm"** - the gap between single-turn tool execution and multi-turn conversational state management.

**Research Finding:** Even GPT-4 and Claude score only **~12%** on agentic memory tasks (BFCL v4 benchmarks).

## Root Causes

1. **Three Overlapping Action Paths** (FastPathRouter + AgentRouter + SystemPlanner) - no shared state
2. **Per-turn State Only** - `turn_state` doesn't persist across conversation
3. **Free-form Tool Returns** - Strings instead of verifiable receipts
4. **No Verification** - Never check if actions actually succeeded

## The Solution

**5-Phase Implementation:**

| Phase | Duration | What |
|-------|----------|------|
| 28.5.1 | 3-4 days | Core schemas + ToolReceipts |
| 28.5.2 | 4-5 days | ActionState with anaphora ("close them") |
| 28.5.3 | 4-5 days | Verification layer |
| 28.5.4 | 5-7 days | Unified routing |
| 28.5.5 | 3-4 days | Regression tests |

## Key Components

```python
# Unified schema for ALL routes
@dataclass
class ActionIntent:
    target: Literal["web", "app", "terminal", "file", "system"]
    operation: Literal["open", "close", "search", "run"]
    entity: str  # "youtube", "chrome"
    query: Optional[str]

# Verifiable tool returns
@dataclass  
class ToolReceipt:
    success: bool
    evidence: Dict[str, Any]  # process_id, window_id
    error_code: Optional[str]
```

## Success Metrics

| Metric | Current | Target |
|--------|---------|--------|
| "also X" follow-up | ~30% | >90% |
| "close them" resolution | ~20% | >85% |
| False confirmations | Unknown | <5% |

## What to Do Next

**Tomorrow (April 9):**
1. Create `core/action/models.py` with ActionIntent, ToolReceipt
2. Refactor `pc_control.py` `open_app()` to return ToolReceipt
3. Write tests

**See full daily note for detailed task breakdown.**

## Research Sources

- **BFCL v4:** https://gorilla.cs.berkeley.edu/blogs/13_bfcl_v3_multi_turn.html
- **ReAct v2:** https://kdcube.tech/ReactV2.html
- **Toolformer:** https://dl.acm.org/doi/10.5555/3666122.3669119
- **AdaQR:** https://aclanthology.org/2024.emnlp-main.746/

## Related

- [[2026-04-08]] - Today's full daily log
- [[Phase_28_5_Action_State_Reform_Plan]] - Complete plan
- [[Maya-Prerequisites-Pre-Implementation-Plan]] - P23 Plan
- [[Maya-Multi-Agent-Architecture-Plan-2025]] - Multi-agent plan

## Tags

#action-state #phase-28-5 #multi-turn #anaphora #verification #bfcl #react
