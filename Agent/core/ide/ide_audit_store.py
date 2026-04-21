"""SQLite-backed audit log and action persistence for IDE subsystems.

Survives process restarts and enables post-hoc audit queries beyond
the in-memory ring buffer. Schema is auto-migrating — no manual upgrades.
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _default_serializer(obj: Any) -> str:
    """JSON serializer for fields that may contain non-serializable types."""
    try:
        return json.dumps(obj)
    except (TypeError, ValueError):
        return json.dumps(str(obj))


def _json_loads(raw: Any) -> Any:
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return raw


class IDEAuditStore:
    """SQLite store for audit events and pending action snapshots."""

    def __init__(
        self,
        db_path: Optional[str] = None,
        *,
        max_audit_events: int = 5000,
        max_pending_actions: int = 1000,
    ) -> None:
        if db_path is None:
            base = os.getenv("MAYA_DATA_DIR", os.path.expanduser("~/.maya"))
            Path(base).mkdir(parents=True, exist_ok=True)
            db_path = os.path.join(base, "ide_audit.db")

        self.db_path = db_path
        self._max_audit_events = max(100, int(max_audit_events))
        self._max_pending_actions = max(10, int(max_pending_actions))
        self._conn: Optional[sqlite3.Connection] = None
        self._init_db()

    # ─── Connection management ────────────────────────────────────────────────

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path, timeout=10.0)
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA busy_timeout=10000")
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def _init_db(self) -> None:
        try:
            with self._get_conn() as conn:
                self._create_tables(conn)
                self._validate_schema(conn)
                conn.execute("SELECT 1")
            logger.info("✅ IDEAuditStore connected to %s", self.db_path)
        except Exception as e:
            logger.error("❌ IDEAuditStore init failed: %s", e)

    def _create_tables(self, conn: sqlite3.Connection) -> None:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS ide_audit_events (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id     TEXT    UNIQUE NOT NULL,
                action_id    TEXT    NOT NULL,
                event_type   TEXT    NOT NULL,
                timestamp    REAL    NOT NULL,
                user_id      TEXT    NOT NULL,
                session_id   TEXT    NOT NULL,
                action_type  TEXT    NOT NULL,
                risk         TEXT    NOT NULL DEFAULT 'unknown',
                idempotency_key  TEXT,
                decided_by   TEXT,
                decided_at   REAL,
                execution_result TEXT,
                error        TEXT,
                trace_id     TEXT,
                task_id      TEXT,
                created_at   TEXT    NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS ide_pending_actions (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                action_id    TEXT    UNIQUE NOT NULL,
                user_id      TEXT    NOT NULL,
                session_id   TEXT    NOT NULL,
                action_type  TEXT    NOT NULL,
                target_id    TEXT    NOT NULL,
                payload      TEXT,
                risk         TEXT    NOT NULL,
                policy_reason TEXT   NOT NULL,
                idempotency_key TEXT NOT NULL,
                requested_at REAL    NOT NULL,
                expires_at   REAL    NOT NULL,
                trace_id     TEXT,
                task_id      TEXT,
                created_at   TEXT    NOT NULL DEFAULT (datetime('now'))
            );

            CREATE INDEX IF NOT EXISTS idx_audit_action_id
                ON ide_audit_events(action_id);
            CREATE INDEX IF NOT EXISTS idx_audit_timestamp
                ON ide_audit_events(timestamp DESC);
            CREATE INDEX IF NOT EXISTS idx_audit_user_id
                ON ide_audit_events(user_id);
            CREATE INDEX IF NOT EXISTS idx_pending_expires
                ON ide_pending_actions(expires_at);
        """)

    def _validate_schema(self, conn: sqlite3.Connection) -> None:
        try:
            cursor = conn.execute("PRAGMA table_info(ide_audit_events)")
            cols = {row[1] for row in cursor.fetchall()}
            for col, ddl in [
                ("trace_id",         "ALTER TABLE ide_audit_events ADD COLUMN trace_id TEXT"),
                ("task_id",          "ALTER TABLE ide_audit_events ADD COLUMN task_id TEXT"),
                ("session_id",       "ALTER TABLE ide_audit_events ADD COLUMN session_id TEXT NOT NULL DEFAULT ''"),
                ("execution_result", "ALTER TABLE ide_audit_events ADD COLUMN execution_result TEXT"),
            ]:
                if col not in cols:
                    conn.execute(ddl)
                    logger.info("🛠️ Added missing column %s.%s", "ide_audit_events", col)
            cursor = conn.execute("PRAGMA table_info(ide_pending_actions)")
            pcols = {row[1] for row in cursor.fetchall()}
            for col, ddl in [
                ("trace_id",    "ALTER TABLE ide_pending_actions ADD COLUMN trace_id TEXT"),
                ("task_id",     "ALTER TABLE ide_pending_actions ADD COLUMN task_id TEXT"),
                ("created_at",  "ALTER TABLE ide_pending_actions ADD COLUMN created_at TEXT NOT NULL DEFAULT (datetime('now'))"),
            ]:
                if col not in pcols:
                    conn.execute(ddl)
                    logger.info("🛠️ Added missing column %s.%s", "ide_pending_actions", col)
            logger.info("✅ IDEAuditStore schema validated")
        except Exception as e:
            logger.warning("Schema validation warning: %s", e)

    # ─── Audit event persistence ──────────────────────────────────────────────

    def write_audit_event(self, event: dict) -> None:
        """Write a single audit event. Silently drops on DB write failure."""
        try:
            with self._get_conn() as conn:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO ide_audit_events
                        (event_id, action_id, event_type, timestamp, user_id,
                         session_id, action_type, risk, idempotency_key,
                         decided_by, decided_at, execution_result, error,
                         trace_id, task_id)
                    VALUES
                        (:event_id, :action_id, :event_type, :timestamp, :user_id,
                         :session_id, :action_type, :risk, :idempotency_key,
                         :decided_by, :decided_at, :execution_result, :error,
                         :trace_id, :task_id)
                    """,
                    {
                        "event_id":     event.get("event_id", f"ev_{int(time.time()*1000)}"),
                        "action_id":    event.get("action_id", ""),
                        "event_type":   event.get("event_type", ""),
                        "timestamp":    event.get("timestamp", time.time()),
                        "user_id":      event.get("user_id", ""),
                        "session_id":   event.get("session_id", ""),
                        "action_type":  event.get("action_type", ""),
                        "risk":         event.get("risk", "unknown"),
                        "idempotency_key": event.get("idempotency_key"),
                        "decided_by":   event.get("decided_by"),
                        "decided_at":   event.get("decided_at"),
                        "execution_result": (
                            _default_serializer(event["execution_result"])
                            if event.get("execution_result") else None
                        ),
                        "error":        event.get("error"),
                        "trace_id":     event.get("trace_id"),
                        "task_id":      event.get("task_id"),
                    },
                )
                # Auto-prune old audit events
                conn.execute(
                    """
                    DELETE FROM ide_audit_events
                    WHERE id NOT IN (
                        SELECT id FROM ide_audit_events
                        ORDER BY timestamp DESC
                        LIMIT ?
                    )
                    """,
                    (self._max_audit_events,),
                )
        except Exception as e:
            logger.warning("write_audit_event failed: %s", e)

    def write_pending_action(self, action: dict) -> None:
        """Upsert a pending action snapshot (called on request/approval/deny)."""
        try:
            with self._get_conn() as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO ide_pending_actions
                        (action_id, user_id, session_id, action_type, target_id,
                         payload, risk, policy_reason, idempotency_key,
                         requested_at, expires_at, trace_id, task_id)
                    VALUES
                        (:action_id, :user_id, :session_id, :action_type, :target_id,
                         :payload, :risk, :policy_reason, :idempotency_key,
                         :requested_at, :expires_at, :trace_id, :task_id)
                    """,
                    {
                        "action_id":       action.get("action_id", ""),
                        "user_id":         action.get("user_id", ""),
                        "session_id":      action.get("session_id", ""),
                        "action_type":     action.get("action_type", ""),
                        "target_id":       action.get("target_id", ""),
                        "payload":         _default_serializer(action.get("payload")),
                        "risk":            action.get("risk", "unknown"),
                        "policy_reason":   action.get("policy_reason", ""),
                        "idempotency_key": action.get("idempotency_key", ""),
                        "requested_at":    action.get("requested_at", time.time()),
                        "expires_at":      action.get("expires_at", time.time()),
                        "trace_id":        action.get("trace_id"),
                        "task_id":         action.get("task_id"),
                    },
                )
                conn.execute(
                    """
                    DELETE FROM ide_pending_actions
                    WHERE id NOT IN (
                        SELECT id FROM ide_pending_actions
                        ORDER BY requested_at DESC
                        LIMIT ?
                    )
                    """,
                    (self._max_pending_actions,),
                )
        except Exception as e:
            logger.warning("write_pending_action failed: %s", e)

    def remove_pending_action(self, action_id: str) -> None:
        """Remove a pending action by ID (called after approve/deny/cancel/expire)."""
        try:
            with self._get_conn() as conn:
                conn.execute(
                    "DELETE FROM ide_pending_actions WHERE action_id = ?",
                    (action_id,),
                )
        except Exception as e:
            logger.warning("remove_pending_action failed: %s", e)

    # ─── Query methods ────────────────────────────────────────────────────────

    def get_audit_events(
        self,
        *,
        action_id: Optional[str] = None,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        event_type: Optional[str] = None,
        limit: int = 200,
    ) -> List[Dict[str, Any]]:
        """Query audit events from SQLite."""
        try:
            conn = self._get_conn()
            sql = ["SELECT * FROM ide_audit_events WHERE 1=1"]
            params: list[Any] = []
            if action_id:
                sql.append("AND action_id = ?")
                params.append(action_id)
            if user_id:
                sql.append("AND user_id = ?")
                params.append(user_id)
            if session_id:
                sql.append("AND session_id = ?")
                params.append(session_id)
            if event_type:
                sql.append("AND event_type = ?")
                params.append(event_type)
            sql.append("ORDER BY timestamp DESC LIMIT ?")
            params.append(max(1, min(int(limit), self._max_audit_events)))

            rows = conn.execute(" ".join(sql), params).fetchall()
            return [self._row_to_audit_event(dict(r)) for r in rows]
        except Exception as e:
            logger.warning("get_audit_events failed: %s", e)
            return []

    def get_pending_actions(self, *, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Load persisted pending actions that have not expired."""
        try:
            conn = self._get_conn()
            sql = [
                "SELECT * FROM ide_pending_actions",
                "WHERE expires_at > ?",
            ]
            params: list[Any] = [time.time()]
            if user_id:
                sql.append("AND user_id = ?")
                params.append(user_id)
            sql.append("ORDER BY requested_at DESC")
            rows = conn.execute(" ".join(sql), params).fetchall()
            return [self._row_to_action(dict(r)) for r in rows]
        except Exception as e:
            logger.warning("get_pending_actions failed: %s", e)
            return []

    def _row_to_audit_event(self, row: dict) -> dict:
        row.pop("id", None)
        row.pop("created_at", None)
        row["execution_result"] = _json_loads(row.pop("execution_result", None))
        return row

    def _row_to_action(self, row: dict) -> dict:
        row.pop("id", None)
        row.pop("created_at", None)
        row["payload"] = _json_loads(row.pop("payload", None))
        return row

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None