"""SQLite-backed checkpoint persistence for recoverable/background tasks."""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

TERMINAL_TASK_STATES = {"COMPLETED", "FAILED", "CANCELLED", "PLAN_FAILED", "STALE"}


class TaskPersistenceManager:
    """Persistence bridge for checkpoints, terminal markers, and recovery discovery."""

    def __init__(self, db_path: Optional[str] = None) -> None:
        if db_path:
            resolved = db_path
        else:
            resolved = os.getenv("DATABASE_URL", "sqlite:///./dev_maya_one.db").replace("sqlite:///", "")
        self.db_path = resolved
        self._create_tables()
        self._validate_schema()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def _create_tables(self) -> None:
        with self._get_conn() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS task_checkpoints (
                    checkpoint_id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    step_id TEXT,
                    payload TEXT NOT NULL,
                    ts TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_task_checkpoints_task_ts
                ON task_checkpoints(task_id, ts DESC);

                CREATE INDEX IF NOT EXISTS idx_task_checkpoints_step_ts
                ON task_checkpoints(step_id, ts DESC);
                """
            )

    def _validate_schema(self) -> None:
        with self._get_conn() as conn:
            cursor = conn.execute("PRAGMA table_info(task_checkpoints)")
            cols = {row[1] for row in cursor.fetchall()}
            if "checkpoint_id" not in cols:
                conn.execute("ALTER TABLE task_checkpoints ADD COLUMN checkpoint_id TEXT")
            if "task_id" not in cols:
                conn.execute("ALTER TABLE task_checkpoints ADD COLUMN task_id TEXT")
            if "step_id" not in cols:
                conn.execute("ALTER TABLE task_checkpoints ADD COLUMN step_id TEXT")
            if "payload" not in cols:
                conn.execute("ALTER TABLE task_checkpoints ADD COLUMN payload TEXT")
            if "ts" not in cols:
                conn.execute("ALTER TABLE task_checkpoints ADD COLUMN ts TEXT")

    async def save_checkpoint(
        self,
        task_id: str,
        step_id: str,
        payload: Dict[str, Any],
        checkpoint_id: Optional[str] = None,
        ts: Optional[str] = None,
    ) -> str:
        normalized_task_id = str(task_id or "").strip()
        if not normalized_task_id:
            raise ValueError("task_id is required")
        normalized_step_id = str(step_id or "").strip() or None
        resolved_checkpoint_id = str(checkpoint_id or f"chk_{uuid.uuid4().hex[:20]}")
        resolved_ts = str(ts or datetime.now(timezone.utc).isoformat())
        payload_json = json.dumps(payload or {}, ensure_ascii=True)

        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO task_checkpoints (checkpoint_id, task_id, step_id, payload, ts)
                VALUES (?, ?, ?, ?, ?)
                """,
                (resolved_checkpoint_id, normalized_task_id, normalized_step_id, payload_json, resolved_ts),
            )
            try:
                conn.execute(
                    """
                    UPDATE tasks
                    SET recovery_checkpoint = ?,
                        persistent = COALESCE(persistent, 1),
                        background_mode = CASE
                            WHEN COALESCE(background_mode, 0) = 1 THEN 1
                            WHEN ? = 'subagent_recovery_checkpoint' THEN 1
                            ELSE COALESCE(background_mode, 0)
                        END,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        payload_json,
                        str((payload or {}).get("event") or ""),
                        resolved_ts,
                        normalized_task_id,
                    ),
                )
            except sqlite3.OperationalError:
                # tasks table may not exist in isolated unit tests.
                pass

        return resolved_checkpoint_id

    async def load_checkpoint(self, step_id_or_task_id: str) -> Optional[Dict[str, Any]]:
        identifier = str(step_id_or_task_id or "").strip()
        if not identifier:
            return None

        with self._get_conn() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                """
                SELECT payload
                FROM task_checkpoints
                WHERE step_id = ?
                ORDER BY ts DESC
                LIMIT 1
                """,
                (identifier,),
            ).fetchone()
            if row is None:
                row = conn.execute(
                    """
                    SELECT payload
                    FROM task_checkpoints
                    WHERE task_id = ?
                    ORDER BY ts DESC
                    LIMIT 1
                    """,
                    (identifier,),
                ).fetchone()

        if row is None:
            return None
        try:
            return json.loads(str(row["payload"] or "{}"))
        except Exception:
            logger.warning("task_persistence_invalid_payload identifier=%s", identifier)
            return None

    async def get_checkpoint(self, identifier: str) -> Optional[Dict[str, Any]]:
        return await self.load_checkpoint(identifier)

    async def read_checkpoint(self, identifier: str) -> Optional[Dict[str, Any]]:
        return await self.load_checkpoint(identifier)

    async def mark_terminal(self, task_id: str, status: str, reason: str) -> bool:
        normalized_task_id = str(task_id or "").strip()
        if not normalized_task_id:
            return False

        resolved_status = str(status or "").strip().upper() or "FAILED"
        resolved_reason = str(reason or "").strip()
        now = datetime.now(timezone.utc).isoformat()

        with self._get_conn() as conn:
            try:
                conn.execute(
                    """
                    UPDATE tasks
                    SET status = ?,
                        error = ?,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (resolved_status, resolved_reason, now, normalized_task_id),
                )
            except sqlite3.OperationalError:
                pass

        return True

    async def recover_background_tasks(self, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        normalized_user_id = str(user_id or "").strip()
        terminal_states = tuple(TERMINAL_TASK_STATES)
        placeholders = ", ".join(["?"] * len(terminal_states))

        sql = (
            f"SELECT id, user_id, status, background_mode, persistent, recovery_checkpoint "
            f"FROM tasks "
            f"WHERE COALESCE(persistent, 0) = 1 "
            f"AND COALESCE(background_mode, 0) = 1 "
            f"AND status NOT IN ({placeholders})"
        )
        params: List[Any] = list(terminal_states)
        if normalized_user_id:
            sql += " AND user_id = ?"
            params.append(normalized_user_id)

        with self._get_conn() as conn:
            conn.row_factory = sqlite3.Row
            try:
                rows = conn.execute(sql, params).fetchall()
            except sqlite3.OperationalError:
                return []

        recovered: List[Dict[str, Any]] = []
        for row in rows:
            checkpoint_payload: Dict[str, Any] = {}
            raw_checkpoint = row["recovery_checkpoint"]
            if raw_checkpoint:
                try:
                    checkpoint_payload = json.loads(str(raw_checkpoint))
                except Exception:
                    checkpoint_payload = {}
            recovered.append(
                {
                    "task_id": row["id"],
                    "user_id": row["user_id"],
                    "status": row["status"],
                    "background_mode": bool(row["background_mode"]),
                    "persistent": bool(row["persistent"]),
                    "recovery_checkpoint": checkpoint_payload,
                }
            )

        return recovered


TaskPersistence = TaskPersistenceManager
