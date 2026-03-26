# Vector Search

## Definition
Semantic similarity search using vector embeddings in Qdrant/ChromaDB to find conceptually related memories.

## Usage in Maya
Part of the [[Hybrid Memory System]]. Searches memory based on semantic meaning rather than exact keyword matches.

## How It Works
1. User query received
2. Query converted to embedding vector
3. Vector compared against stored document vectors
4. Returns semantically similar memories
5. Results ranked by cosine similarity

## Advantages
- Finds conceptually related content
- Tolerates phrasing variations
- Understands synonyms and related concepts

## Limitations
- Computationally expensive (requires embeddings)
- May miss exact keyword matches
- Needs hybrid approach with keyword search

## Related
- [[Hybrid Memory System]]
- [[FTS5 Keyword Search]]
- [[HybridMemoryManager]]
- [[7-Layer Runtime Chain]]
