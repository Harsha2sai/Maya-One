-- Migration 0002: Create Memory FTS5 Table
-- SQLite Full-Text Search for keyword-based memory retrieval

CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(
    id UNINDEXED,
    user_id UNINDEXED,
    text,
    source,
    metadata UNINDEXED,
    created_at UNINDEXED
);
