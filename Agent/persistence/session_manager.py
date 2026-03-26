import sqlite3
import json
import uuid
import logging
from typing import List, Dict, Optional, Any
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("session_manager")

class SessionManager:
    def __init__(self, db_path: str = "sessions.db"):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self):
        return sqlite3.connect(self.db_path)

    def _init_db(self):
        """Initialize the database with the schema."""
        schema_path = Path(__file__).parent / "schema.sql"
        if not schema_path.exists():
            logger.error(f"Schema file not found at {schema_path}")
            raise FileNotFoundError(f"Schema file not found at {schema_path}")

        try:
            with open(schema_path, "r") as f:
                schema = f.read()
            
            with self._get_connection() as conn:
                conn.executescript(schema)
                conn.commit()
            logger.info(f"Database initialized at {self.db_path}")
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            raise

    def create_session(self, metadata: Optional[Dict[str, Any]] = None) -> str:
        """Create a new session and return its ID."""
        session_id = str(uuid.uuid4())
        metadata_json = json.dumps(metadata) if metadata else None
        
        try:
            with self._get_connection() as conn:
                conn.execute(
                    "INSERT INTO sessions (id, metadata) VALUES (?, ?)",
                    (session_id, metadata_json)
                )
                conn.commit()
            logger.info(f"Created session {session_id}")
            return session_id
        except Exception as e:
            logger.error(f"Failed to create session: {e}")
            raise

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve session details."""
        try:
            with self._get_connection() as conn:
                cursor = conn.execute(
                    "SELECT id, created_at, updated_at, metadata FROM sessions WHERE id = ?",
                    (session_id,)
                )
                row = cursor.fetchone()
                
            if row:
                return {
                    "id": row[0],
                    "created_at": row[1],
                    "updated_at": row[2],
                    "metadata": json.loads(row[3]) if row[3] else None
                }
            return None
        except Exception as e:
            logger.error(f"Failed to get session {session_id}: {e}")
            return None

    def add_message(
        self, 
        session_id: str, 
        role: str, 
        content: Optional[str] = None, 
        tool_calls: Optional[List[Dict]] = None,
        tool_call_id: Optional[str] = None
    ) -> str:
        """Add a message to the session."""
        message_id = str(uuid.uuid4())
        tool_calls_json = json.dumps(tool_calls) if tool_calls else None
        
        try:
            with self._get_connection() as conn:
                # Ensure session exists
                session = conn.execute("SELECT 1 FROM sessions WHERE id = ?", (session_id,)).fetchone()
                if not session:
                    # Auto-create session if it doesn't exist? For now, raise error or create strictly.
                    # Let's auto-create for robustness if missing, or maybe just fail.
                    # Safe approach: fail. The system should create session first.
                    raise ValueError(f"Session {session_id} does not exist.")

                created_at = datetime.now(timezone.utc).isoformat()
                conn.execute(
                    """
                    INSERT INTO messages (id, session_id, role, content, tool_calls, tool_call_id, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (message_id, session_id, role, content, tool_calls_json, tool_call_id, created_at)
                )
                
                # Update session updated_at
                conn.execute(
                    "UPDATE sessions SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (session_id,)
                )
                conn.commit()
            return message_id
        except Exception as e:
            logger.error(f"Failed to add message to session {session_id}: {e}")
            raise

    def get_recent_history(self, session_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Get the most recent N messages for a session, ordered chrono."""
        try:
            with self._get_connection() as conn:
                # Get last N messages
                cursor = conn.execute(
                    """
                    SELECT role, content, tool_calls, tool_call_id, created_at 
                    FROM messages 
                    WHERE session_id = ? 
                    ORDER BY created_at DESC 
                    LIMIT ?
                    """,
                    (session_id, limit)
                )
                rows = cursor.fetchall()
                
            # Reverse to get chronological order
            history = []
            for row in reversed(rows):
                msg = {
                    "role": row[0],
                    "content": row[1],
                }
                if row[2]:
                    msg["tool_calls"] = json.loads(row[2])
                if row[3]:
                    msg["tool_call_id"] = row[3]
                history.append(msg)
                
            return history
        except Exception as e:
            logger.error(f"Failed to get history for session {session_id}: {e}")
            return []
