# FTS5 Keyword Search

## Definition
Full-text search using SQLite FTS5 (Full-Text Search version 5) for exact/keyword-based memory retrieval.

## Usage in Maya
Part of the [[Hybrid Memory System]] for exact keyword matching. Complements vector search for precise retrievals.

## How It Works
1. User query received
2. Parse query into terms
3. Search against FTS5 index
4. Rank by relevance score
5. Return exact keyword matches

## Advantages
- Fast performance
- Exact keyword matching
- Works with partial matches and stemming
- SQLite native (no external dependencies)

## Limitations
- Requires exact keywords
- Doesn't understand semantic meaning
- May miss conceptually related content

## Known Issues
- Currently running for trivial messages causing unnecessary DB calls (see [[FTS5 Memory Search Running Unnecessarily]])

## Related
- [[Hybrid Memory System]]
- [[Vector Search]]
- [[HybridMemoryManager]]
- [[Intent-First Routing]]
