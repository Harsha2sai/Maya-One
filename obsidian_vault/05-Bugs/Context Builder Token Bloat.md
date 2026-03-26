# Bug: Context Builder Token Bloat

## Description
**RESOLVED - Bug documentation was misleading, not the code**

Memory section correctly limited to 2000 tokens. Total context budget is 12000 (model window cap). Both are correct and intentional.

## Root Cause
- Bug report claimed "total context < 2000" but this was false
- Confusion between memory tier budget (2000) vs total context budget (12000)

## Affected Components
- ContextGuard correctly enforces tiered limits:
  - Tier 1 System: 1500 tokens
  - Tier 2 Recent History: 4000 tokens
  - Tier 3 Summary: ~3000 tokens (rolling)
  - Tier 4 Memory: **2000 tokens** ✅ (correctly limited)
  - **Total: Up to 12000** ✅ (model window cap, correct)
- `MAX_MEMORY_TOKENS=2000` in `.env` - working correctly
- `MAX_CONTEXT_TOKENS=12000` in `.env` - model window, correct

## Fix Applied
✅ Phase 6 tiered ContextGuard correctly implemented:
- **Memory tier (Tier 4) limited to 2000 tokens** ✅ working as designed
- Total context budget 12000 tokens ✅ model window cap (not a bug)
- Removed inline context fallback ✅ done
- Enforces proper tool gating ✅ done

## Status
🟢 CLOSED - Working as Designed

## Misunderstanding Clarified
- ❌ **Incorrect claim**: "Total context budget < 2000 tokens"
- ✅ **Reality**: Only memory section is 2000 tokens (Tier 4)
- ✅ **Reality**: Total context budget is 12000 (model window cap)
- ✅ **Both limits are correct and intentional**

## Related
- [[Context Gating and Tool Safety]]
- [[Hybrid Memory System]]
- [[ContextBuilder]]
- [[Memory Context Guard]]
