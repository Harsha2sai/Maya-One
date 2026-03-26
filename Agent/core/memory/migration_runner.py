"""
Migration runner for keyword memory database schema updates.

Handles safe FTS5 table rebuilds since FTS tables cannot be altered.
"""

import logging
import sqlite3
from pathlib import Path
from typing import List, Tuple

logger = logging.getLogger(__name__)


class MigrationRunner:
    """Manages database schema migrations for keyword memory store."""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        
    def needs_migration(self) -> bool:
        """Check if database needs migration by inspecting schema."""
        if not Path(self.db_path).exists():
            logger.info("Database does not exist yet, no migration needed")
            return False
            
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Check if memory_fts table exists
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='memory_fts'
            """)
            
            if not cursor.fetchone():
                logger.info("memory_fts table does not exist, no migration needed")
                conn.close()
                return False
            
            # Inspect schema
            cursor.execute("PRAGMA table_info(memory_fts)")
            columns = [row[1] for row in cursor.fetchall()]
            conn.close()
            
            # Check if user_id column exists
            if 'user_id' not in columns:
                logger.warning(f"Schema missing user_id column. Current columns: {columns}")
                return True
            
            logger.info("Schema is up to date")
            return False
            
        except Exception as e:
            logger.error(f"Error checking migration status: {e}")
            return False
    
    def run_migration(self) -> bool:
        """
        Execute safe FTS5 rebuild migration.
        
        FTS5 tables cannot be altered, so we must:
        1. Create new table with correct schema
        2. Copy existing data
        3. Drop old table
        4. Rename new table
        
        Returns:
            bool: True if migration successful, False otherwise
        """
        if not self.needs_migration():
            return True
        
        logger.info("Starting FTS5 schema migration...")
        
        try:
            conn = sqlite3.connect(self.db_path)
            conn.execute("BEGIN TRANSACTION")
            
            # Step 1: Create new table with correct schema
            logger.info("Creating memory_fts_new with updated schema...")
            conn.execute("""
                CREATE VIRTUAL TABLE memory_fts_new USING fts5(
                    id UNINDEXED,
                    user_id UNINDEXED,
                    text,
                    source,
                    metadata UNINDEXED,
                    created_at UNINDEXED
                )
            """)
            
            # Step 2: Copy existing data (set user_id = 'unknown' for legacy data)
            logger.info("Copying existing data to new table...")
            conn.execute("""
                INSERT INTO memory_fts_new (id, user_id, text, source, metadata, created_at)
                SELECT id, 'unknown', text, source, metadata, created_at
                FROM memory_fts
            """)
            
            # Get count for verification
            cursor = conn.execute("SELECT COUNT(*) FROM memory_fts")
            old_count = cursor.fetchone()[0]
            
            cursor = conn.execute("SELECT COUNT(*) FROM memory_fts_new")
            new_count = cursor.fetchone()[0]
            
            if old_count != new_count:
                raise Exception(f"Data copy mismatch: {old_count} rows in old table, {new_count} in new")
            
            logger.info(f"Successfully copied {new_count} rows")
            
            # Step 3: Drop old table
            logger.info("Dropping old table...")
            conn.execute("DROP TABLE memory_fts")
            
            # Step 4: Rename new table
            logger.info("Renaming new table to memory_fts...")
            conn.execute("ALTER TABLE memory_fts_new RENAME TO memory_fts")
            
            conn.execute("COMMIT")
            conn.close()
            
            logger.info("✅ Migration completed successfully")
            return True
            
        except Exception as e:
            logger.error(f"❌ Migration failed: {e}")
            try:
                conn.execute("ROLLBACK")
                conn.close()
            except:
                pass
            return False
