import sqlite3
import os

DB_PATH = "dev_maya_one.db"
MIGRATION_PATH = "migrations/0001_create_tasks.sql"

def init_db():
    print(f"🔧 Initializing database: {DB_PATH}")
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
        print(f"🗑️ Removed existing database.")

    with open(MIGRATION_PATH, 'r') as f:
        sql = f.read()

    with sqlite3.connect(DB_PATH) as conn:
        conn.executescript(sql)
        conn.execute("PRAGMA journal_mode=WAL;")
        print("✅ Database initialized and WAL mode enabled.")

if __name__ == "__main__":
    init_db()
