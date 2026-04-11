"""SQLite-backed checkpoint persistence for recoverable/background tasks."""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

TERMINAL_TASK_STATES = {"COMPLETED", "FAILED", "CANCELLED", "PLAN_FAILED", "STALE"}


class TaskPersistenceManager:
    """Persistence bridge for checkpoints, terminal markers, and recovery discovery."""

    def __init__(self, db_path: Optional[str] = None) -> None:
        resolved = db_path or os.getenv("DATABASE_URL", "sqlite:///./dev_maya_one.db").replace("sqlite:///", "")
        self.db_path = resolved
        self._create_tables()

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
        resolved_step_id = str(step_id or "").strip() or None
        resolved_checkpoint_id = str(checkpoint_id or f"chk_{uuid.uuid4().hex[:20]}")
        resolved_ts = str(ts or datetime.now(timezone.utc).isoformat())
        payload_json = json.dumps(payload or {}, ensure_ascii=True)

        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO task_checkpoints (checkpoint_id, task_id, step_id, payload, ts)
                VALUES (?, ?, ?, ?, ?)
                """,
                (resolved_checkpoint_id, normalized_task_id, resolved_step_id, payload_json, resolved_ts),
            )

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
            return None

    async def get_checkpoint(self, identifier: str) -> Optional[Dict[str, Any]]:
        return await self.load_checkpoint(identifier)

    async def read_checkpoint(self, identifier: str) -> Optional[Dict[str, Any]]:
        return await self.load_checkpoint(identifier)

    async def mark_terminal(self, task_id: str, status: str, reason: str) -> bool:
        normalized_task_id = str(task_id or "").strip()
        if not normalized_task_id:
            return False

        now = datetime.now(timezone.utc).isoformat()
        with self._get_conn() as conn:
            try:
                conn.execute(
                    """
                    UPDATE tasks
                    SET status = ?, error = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (str(status or "FAILED").strip().upper(), str(reason or "").strip(), now, normalized_task_id),
                )
            except sqlite3.OperationalError:
                pass

        return True

    async def recover_background_tasks(self, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        normalized_user_id = str(user_id or "").strip()
        terminal_states = tuple(TERMINAL_TASK_STATES)
        placeholders = ", ".join(["?"] * len(terminal_states))

        extra_columns = {"persistent": "0", "background_mode": "0", "cron_expression": "NULL"}
        with self._get_conn() as conn:
            conn.row_factory = sqlite3.Row
            try:
                available_columns = {row["name"] for row in conn.execute("PRAGMA table_info(tasks)").fetchall()}
            except sqlite3.OperationalError:
                return []

        selected_columns = ["id", "user_id", "status", "metadata"]
        for column_name, fallback in extra_columns.items():
            if column_name in available_columns:
                selected_columns.append(column_name)
            else:
                selected_columns.append(f"{fallback} AS {column_name}")

        sql = (
            f"SELECT {', '.join(selected_columns)} FROM tasks "
            f"WHERE status NOT IN ({placeholders})"
        )
        params: List[Any] = list(terminal_states)
        if normalized_user_id:
            sql += " AND user_id = ?"
            params.append(normalized_user_id)

        recovered: List[Dict[str, Any]] = []
        with self._get_conn() as conn:
            conn.row_factory = sqlite3.Row
            try:
                rows = conn.execute(sql, params).fetchall()
            except sqlite3.OperationalError:
                return []

        for row in rows:
            metadata: Dict[str, Any] = {}
            raw_metadata = row["metadata"]
            if raw_metadata:
                try:
                    metadata = json.loads(str(raw_metadata))
                except Exception:
                    metadata = {}
            row_background_mode = bool(int(row["background_mode"] or 0))
            row_persistent = bool(int(row["persistent"] or 0))
            metadata_background = bool(metadata.get("scheduled_task") or metadata.get("background_mode"))
            if not (metadata_background or row_background_mode or row_persistent):
                continue
            recovered.append(
                {
                    "task_id": row["id"],
                    "user_id": row["user_id"],
                    "status": row["status"],
                    "metadata": metadata,
                    "persistent": row_persistent,
                    "background_mode": row_background_mode,
                    "cron_expression": row["cron_expression"],
                }
            )
        return recovered


TaskPersistence = TaskPersistenceManager
