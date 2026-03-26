# Hybrid Memory System

## Purpose
Combines vector search (semantic) with FTS5 keyword search (exact) for optimal memory retrieval. Small-talk queries bypass memory to save latency.

## Components
**HybridMemoryManager**
- Combines:
  - Vector search (Qdrant/ChromaDB) for semantic similarity
  - FTS5 keyword search for exact matches
- Prefers one or both based on query type
- Small-talk queries bypass memory entirely

**ContextGuard** (`core/context/final_context_guard.py`)
- Enforces token limits < 2000 tokens (reduced from 12000)
- Prevents context contamination

## Internal Logic
1. Query enters memory system
2. Small-talk detection: simple patterns like "hi", "hello" bypass
3. Normal queries → both search methods
4. Results ranked and merged
5. ContextGuard validates token budget
6. Result passed to LLM context

## Dependencies
- [[SmartLLM]]
- [[Context Builder]]
- [[Intent-First Routing]]

## Known Issues
- FTS5 memory search running unnecessarily for trivial messages (FIX IN PROGRESS)

## Related
- [[Vector Search]]
- [[FTS5 Keyword Search]]
- [[Memory Context Guard]]
- [[Small-Talk Bypass]]
