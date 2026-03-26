# Memory Context Guard

## Definition
Enforces token budget limits for memory context retrieval to prevent context bloat.

## Usage in Maya
Part of [[Phase 6: Context Gating & Tool Safety]] enforcement. Validates memory results before adding to LLM context.

## Configuration
Token budget reduced from 12000 to < 2000 tokens in Phase 6.

## How It Works
1. Memory retrieval receives results
2. Token count calculated
3. If exceeds budget → prune/trim results
4. Return within acceptable limit
5. Log warning if pruning required

## Related
- [[Context Gating and Tool Safety]]
- [[Hybrid Memory System]]
- [[Context Builder Token Bloat]]
- [[Phase Architecture]] Phase 6
