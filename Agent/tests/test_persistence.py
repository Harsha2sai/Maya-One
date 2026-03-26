import unittest
import os
import sqlite3
import shutil
from persistence.session_manager import SessionManager

class TestSessionManager(unittest.TestCase):
    def setUp(self):
        self.db_path = "test_sessions.db"
        self.manager = SessionManager(db_path=self.db_path)

    def tearDown(self):
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_create_session(self):
        session_id = self.manager.create_session(metadata={"user": "test_user"})
        self.assertIsNotNone(session_id)
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT id, metadata FROM sessions WHERE id = ?", (session_id,))
        row = cursor.fetchone()
        conn.close()
        
        self.assertIsNotNone(row)
        self.assertEqual(row[0], session_id)
        self.assertIn("test_user", row[1])

    def test_add_message_and_retrieve_history(self):
        session_id = self.manager.create_session()
        
        msg1_id = self.manager.add_message(session_id, "user", "Hello")
        msg2_id = self.manager.add_message(session_id, "assistant", "Hi there")
        
        history = self.manager.get_recent_history(session_id)
        
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0]["role"], "user")
        self.assertEqual(history[0]["content"], "Hello")
        self.assertEqual(history[1]["role"], "assistant")
        self.assertEqual(history[1]["content"], "Hi there")

    def test_history_limit(self):
        session_id = self.manager.create_session()
        for i in range(10):
            self.manager.add_message(session_id, "user", f"Message {i}")
            
        history = self.manager.get_recent_history(session_id, limit=5)
        self.assertEqual(len(history), 5)
        self.assertEqual(history[0]["content"], "Message 5")
        self.assertEqual(history[4]["content"], "Message 9")

if __name__ == "__main__":
    unittest.main()
