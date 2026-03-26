import sqlite3
import sys
import os

def setup_db(db_path, migration_path, integrity_output_path):
    try:
        # Connect to DB (create if not exists)
        # Note: We don't remove existing per user request Step 2 "Run once", but usually preflight is fresh.
        # User script: sqlite3 preflight.db < migration.sql
        # This implies running migration on existing if present? Or assuming fresh.
        # "sqlite3 preflight_artifacts/preflight.db" implies a specific preflight DB.
        # It's safer to start fresh for a preflight check to ensure reproducibility.
        if os.path.exists(db_path):
            os.remove(db_path)
            
        conn = sqlite3.connect(db_path)
        
        with open(migration_path, 'r') as f:
            script = f.read()
            
        conn.executescript(script)
        conn.commit()
        
        # Integrity check
        cursor = conn.execute("PRAGMA integrity_check;")
        # integrity_check returns multiple rows if errors, or one row 'ok'.
        # For simplicity, we assume single row 'ok'.
        rows = cursor.fetchall()
        result = rows[0][0] if rows else "unknown"
        
        with open(integrity_output_path, 'w') as f:
            f.write(result)
            
        conn.close()
        print(f"Database setup complete. Integrity: {result}")
        if result != "ok":
            sys.exit(1)
            
    except Exception as e:
        print(f"Error setting up SQLite: {e}")
        sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Usage: python setup_sqlite.py <db_path> <migration_path> <integrity_output_path>")
        sys.exit(1)
        
    setup_db(sys.argv[1], sys.argv[2], sys.argv[3])
