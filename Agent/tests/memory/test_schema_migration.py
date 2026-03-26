"""
Test schema migration for keyword memory store.

Verifies that the migration runner correctly upgrades old databases
to include the user_id column in the FTS5 table.
"""

import pytest
import sqlite3
import tempfile
from pathlib import Path
from core.memory.keyword_store import KeywordStore
from core.memory.migration_runner import MigrationRunner


def test_migration_from_old_schema():
    """Test migration from old schema (no user_id) to new schema (with user_id)."""
    
    # Create temporary database with OLD schema
    with tempfile.NamedTemporaryFile(delete=False, suffix='.db') as tmp:
        db_path = tmp.name
    
    try:
        # Create old schema manually
        conn = sqlite3.connect(db_path)
        conn.execute("""
            CREATE VIRTUAL TABLE memory_fts USING fts5(
                id UNINDEXED,
                text,
                source,
                metadata UNINDEXED,
                created_at UNINDEXED
            )
        """)
        
        # Insert test data
        conn.execute("""
            INSERT INTO memory_fts (id, text, source, metadata, created_at)
            VALUES ('test-1', 'test memory', 'test', '{}', '2024-01-01')
        """)
        conn.commit()
        conn.close()
        
        # Verify old schema (no user_id column)
        migrator = MigrationRunner(db_path)
        assert migrator.needs_migration() == True, "Should detect missing user_id column"
        
        # Run migration
        success = migrator.run_migration()
        assert success == True, "Migration should succeed"
        
        # Verify new schema has user_id
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(memory_fts)")
        columns = [row[1] for row in cursor.fetchall()]
        
        assert 'user_id' in columns, "user_id column should exist after migration"
        assert 'id' in columns, "id column should still exist"
        assert 'text' in columns, "text column should still exist"
        
        # Verify data was preserved
        cursor.execute("SELECT id, user_id, text FROM memory_fts WHERE id = 'test-1'")
        row = cursor.fetchone()
        
        assert row is not None, "Data should be preserved"
        assert row[0] == 'test-1', "ID should match"
        assert row[1] == 'unknown', "user_id should be set to 'unknown' for legacy data"
        assert row[2] == 'test memory', "Text should be preserved"
        
        conn.close()
        
    finally:
        # Cleanup
        Path(db_path).unlink(missing_ok=True)


def test_keyword_store_with_migration():
    """Test that KeywordStore automatically runs migration on init."""
    
    # Create temporary database with OLD schema
    with tempfile.NamedTemporaryFile(delete=False, suffix='.db') as tmp:
        db_path = tmp.name
    
    try:
        # Create old schema manually
        conn = sqlite3.connect(db_path)
        conn.execute("""
            CREATE VIRTUAL TABLE memory_fts USING fts5(
                id UNINDEXED,
                text,
                source,
                metadata UNINDEXED,
                created_at UNINDEXED
            )
        """)
        conn.commit()
        conn.close()
        
        # Initialize KeywordStore (should trigger migration)
        store = KeywordStore(db_path=db_path)
        
        # Verify schema was updated
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(memory_fts)")
        columns = [row[1] for row in cursor.fetchall()]
        conn.close()
        
        assert 'user_id' in columns, "KeywordStore should have run migration"
        
    finally:
        # Cleanup
        Path(db_path).unlink(missing_ok=True)


def test_no_migration_needed_for_new_db():
    """Test that migration is skipped for databases with correct schema."""
    
    with tempfile.NamedTemporaryFile(delete=False, suffix='.db') as tmp:
        db_path = tmp.name
    
    try:
        # Create KeywordStore (will create correct schema)
        store = KeywordStore(db_path=db_path)
        
        # Check migration status
        migrator = MigrationRunner(db_path)
        assert migrator.needs_migration() == False, "Should not need migration for new DB"
        
    finally:
        # Cleanup
        Path(db_path).unlink(missing_ok=True)
