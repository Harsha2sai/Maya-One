import logging
import sqlite3
import json
from pathlib import Path
from typing import List, Dict, Set, Any
from core.memory.memory_models import MemoryItem
from core.memory.migration_runner import MigrationRunner

logger = logging.getLogger(__name__)

class KeywordStore:
    """SQLite FTS5-based keyword memory store for exact text matching."""
    
    def __init__(self, db_path: str = None):
        if db_path is None:
            db_path = str(Path.home() / ".maya" / "memory" / "keyword.db")
        
        self.db_path = db_path
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        
        # Run migration before initializing database
        logger.info("Checking for schema migrations...")
        migrator = MigrationRunner(self.db_path)
        if migrator.needs_migration():
            logger.warning("Database schema migration required")
            if not migrator.run_migration():
                logger.error("Migration failed! Database may be in inconsistent state")
        
        self._init_db()
        self._fts_columns = self._load_fts_columns()
        logger.info(f"Keyword store initialized at {db_path}")
    
    def _init_db(self):
        """Initialize FTS5 table if it doesn't exist."""
        with sqlite3.connect(self.db_path) as conn:
            # Create FTS5 table directly (don't use migration file for now)
            conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(
                    id UNINDEXED,
                    user_id UNINDEXED,
                    text,
                    source,
                    metadata UNINDEXED,
                    created_at UNINDEXED
                )
            """)
            conn.commit()

    def _load_fts_columns(self) -> Set[str]:
        """Read current FTS column names for schema-compatible queries/inserts."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("PRAGMA table_info(memory_fts)")
                return {str(row[1]) for row in cursor.fetchall()}
        except Exception as e:
            logger.warning(f"Failed to inspect memory_fts schema: {e}")
            return set()

    def _user_column(self) -> str:
        """Support both legacy and current user column names."""
        if "user_id" in self._fts_columns:
            return "user_id"
        if "user" in self._fts_columns:
            return "user"
        return ""
    
    def add_memory(self, memory: MemoryItem) -> bool:
        """Add a memory item to the keyword store."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                user_column = self._user_column()
                if user_column:
                    conn.execute(
                        f"""
                        INSERT INTO memory_fts (id, {user_column}, text, source, metadata, created_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            memory.id,
                            memory.metadata.get("user_id", "unknown"),
                            memory.text,
                            memory.source,
                            json.dumps(memory.metadata),
                            memory.created_at.isoformat(),
                        ),
                    )
                else:
                    conn.execute(
                        """
                        INSERT INTO memory_fts (id, text, source, metadata, created_at)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            memory.id,
                            memory.text,
                            memory.source,
                            json.dumps(memory.metadata),
                            memory.created_at.isoformat(),
                        ),
                    )
                conn.commit()
            
            logger.debug(f"Added memory {memory.id} to keyword store")
            return True
            
        except Exception as e:
            logger.error(f"Failed to add memory to keyword store: {e}")
            return False
    
    def _is_valid_fts_query(self, query: str) -> bool:
        """Validate FTS5 query string."""
        if not query:
            return False
        if len(query.strip()) < 3:
            return False
        return True

    def keyword_search(
        self,
        query: str,
        k: int = 5,
        user_id: str | None = None,
        session_id: str | None = None,
    ) -> List[Dict[str, Any]]:
        """
        Perform FTS5 keyword search.
        Returns list of {id, text, metadata} dicts.
        """
        from core.memory.fts_query_sanitizer import sanitize_fts_query
        
        safe_query = sanitize_fts_query(query)
        if not safe_query:
            return []

        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                user_column = self._user_column()

                if user_id and not user_column:
                    logger.warning(
                        "Keyword search requested user scope but no user column is present; returning empty result."
                    )
                    return []

                if user_id and user_column:
                    cursor = conn.execute(
                        f"""
                        SELECT *, rank
                        FROM memory_fts
                        WHERE memory_fts MATCH ?
                          AND {user_column} = ?
                        ORDER BY rank
                        LIMIT ?
                        """,
                        (safe_query, user_id, k),
                    )
                else:
                    cursor = conn.execute(
                        """
                        SELECT *, rank
                        FROM memory_fts
                        WHERE memory_fts MATCH ?
                        ORDER BY rank
                        LIMIT ?
                        """,
                        (safe_query, k),
                    )
                
                results = []
                for row in cursor:
                    metadata = json.loads(row['metadata']) if row['metadata'] else {}
                    user_value = row["user_id"] if "user_id" in row.keys() else (
                        row["user"] if "user" in row.keys() else metadata.get("user_id", "unknown")
                    )
                    if session_id and str(metadata.get("session_id") or "") != str(session_id):
                        continue
                    results.append({
                        'id': row['id'],
                        'text': row['text'],
                        'metadata': {
                            'user_id': user_value,
                            'source': row['source'],
                            'created_at': row['created_at'],
                            **metadata
                        },
                        'rank': row['rank']
                    })
                
                logger.debug(f"Keyword search returned {len(results)} results")
                return results

        except sqlite3.OperationalError as e:
            logger.warning(f"Keyword search schema mismatch, reloading columns: {e}")
            self._fts_columns = self._load_fts_columns()
            return []
        except Exception as e:
            logger.error(f"Keyword search failed: {e}")
            return []
    
    def delete_memory(self, memory_id: str) -> bool:
        """Delete a memory by ID."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("DELETE FROM memory_fts WHERE id = ?", (memory_id,))
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to delete memory {memory_id}: {e}")
            return False
    
    def count(self) -> int:
        """Return total number of memories."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("SELECT COUNT(*) FROM memory_fts")
                return cursor.fetchone()[0]
        except Exception as e:
            logger.error(f"Failed to count memories: {e}")
            return 0
