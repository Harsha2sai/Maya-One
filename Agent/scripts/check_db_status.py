import sqlite3
import os

DB_PATH = "dev_maya_one.db"

def check_status():
    if not os.path.exists(DB_PATH):
        print("❌ DB not found!")
        return

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        
        print("--- Tasks ---")
        tasks = conn.execute("SELECT id, status, title FROM tasks").fetchall()
        for t in tasks:
            print(f"ID: {t['id']}, Status: {t['status']}, Title: {t['title']}")
            
        print("\n--- Task Steps ---")
        steps = conn.execute("SELECT task_id, seq, status, worker FROM task_steps").fetchall()
        for s in steps:
            print(f"TaskID: {s['task_id']}, Seq: {s['seq']}, Status: {s['status']}, Worker: {s['worker']}")

if __name__ == "__main__":
    check_status()
