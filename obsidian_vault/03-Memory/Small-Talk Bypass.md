# Small-Talk Bypass

## Definition
Detection and bypass mechanism for trivial messages that don't require memory retrieval.

## Usage in Maya
Optimization feature in [[Hybrid Memory System]] to save latency on trivial queries.

## How It Works
1. Message received
2. Pattern matching for small-talk ("hi", "hello", "hey", etc.)
3. If trivial → bypass memory system
4. Return empty context
5. Allow LLM to respond directly

## Benefits
- Saves ~3.8s latency on first token
- Reduces unnecessary DB calls
- Prevents embeddings generation
- Reduces planner noise

## Known Issues
- Detection not comprehensive (see [[FTS5 Memory Search Running Unnecessarily]])

## Related
- [[Hybrid Memory System]]
- [[Intent-First Routing]]
- [[FTS5 Memory Search Running Unnecessarily]]
- [[FTS5 Keyword Search]]
