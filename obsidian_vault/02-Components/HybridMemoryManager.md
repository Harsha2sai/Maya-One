# HybridMemoryManager

## Responsibility
Combines vector search (semantic) with FTS5 keyword search (exact) for optimal memory retrieval. Implements small-talk bypass to save latency.

## Inputs
- User query
- Context from AgentOrchestrator

## Outputs
- Retrieved memories (relevant history, context)
- Ranked results (vector + keyword merged)
- Empty result for small-talk (bypass)

## Internal Logic
1. Small-talk detection (patterns like "hi", "hello")
2. If small-talk → bypass memory, return empty
3. Normal query:
   - Vector search (semantic similarity)
   - FTS5 keyword search (exact matches)
4. Rank and merge results
5. ContextGuard validates token budget
6. Return results

## Known Issues
- FTS5 memory search running unnecessarily for trivial messages
- Causes unnecessary DB calls and embeddings

## Dependencies
- [[Vector Search]] (Qdrant/ChromaDB)
- [[FTS5 Keyword Search]] (SQLite FTS5)
- [[ContextGuard]]

## Related
- [[Hybrid Memory System]]
- [[Intent-First Routing]]
- [[Small-Talk Bypass]]
