"""Task persistence and restart recovery helpers (SQLite-first)."""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from core.tasks.task_models import Task, TaskStatus
from core.tasks.task_store import TaskStore
from core.telemetry.runtime_metrics import RuntimeMetrics

logger = logging.getLogger(__name__)

TERMINAL_TASK_STATUSES = {
    TaskStatus.COMPLETED,
    TaskStatus.FAILED,
    TaskStatus.CANCELLED,
    TaskStatus.PLAN_FAILED,
    TaskStatus.STALE,
}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class TaskPersistence:
    """Persistence facade for checkpoints, resume markers, and terminal state marks."""

    def __init__(self, *, store: Optional[TaskStore] = None) -> None:
        self.store = store or TaskStore()

    async def save_checkpoint(
        self,
        task_id: str,
        step_id: str,
        payload: Dict[str, Any],
        checkpoint_id: str | None = None,
        ts: str | None = None,
    ) -> str:
        task = await self.store.get_task(task_id)
        if task is None:
            raise LookupError(f"task_not_found:{task_id}")
        checkpoint_id = str(checkpoint_id or f"chk_{uuid.uuid4().hex[:12]}")
        timestamp = str(ts or _utc_now_iso())
        task.metadata = task.metadata or {}
        checkpoints = task.metadata.get("checkpoints")
        if not isinstance(checkpoints, list):
            checkpoints = []
        checkpoints.append(
            {
                "checkpoint_id": checkpoint_id,
                "step_id": str(step_id or ""),
                "payload": dict(payload or {}),
                "ts": timestamp,
            }
        )
        # Keep latest 50 checkpoints/task to bound metadata growth.
        task.metadata["checkpoints"] = checkpoints[-50:]
        task.metadata["last_checkpoint_id"] = checkpoint_id
        task.metadata["last_checkpoint_ts"] = timestamp
        task.updated_at = datetime.now(timezone.utc)
        await self.store.update_task(task)
        return checkpoint_id

    async def load_recoverable_tasks(self) -> List[Task]:
        backend = getattr(self.store, "backend", None)
        if backend is not None and hasattr(backend, "_get_conn"):
            try:
                conn = backend._get_conn()
                try:
                    terminal = [s.value for s in TERMINAL_TASK_STATUSES]
                    placeholders = ", ".join(["?"] * len(terminal))
                    rows = conn.execute(
                        f"SELECT id FROM tasks WHERE status NOT IN ({placeholders}) ORDER BY updated_at DESC",
                        terminal,
                    ).fetchall()
                finally:
                    conn.close()
                recoverable: List[Task] = []
                for row in rows:
                    task = await self.store.get_task(str(row[0]))
                    if task is None:
                        continue
                    metadata = task.metadata or {}
                    if metadata.get("resume_disabled"):
                        continue
                    recoverable.append(task)
                return recoverable
            except Exception as err:
                logger.warning("task_recovery_scan_failed error=%s", err)
        # Conservative fallback when full scan is not supported.
        return []

    async def mark_resumed(self, task_id: str, worker_id: str) -> bool:
        task = await self.store.get_task(task_id)
        if task is None:
            RuntimeMetrics.observe("recovery_success_rate", 0.0)
            return False
        task.metadata = task.metadata or {}
        resumes = task.metadata.get("resume_events")
        if not isinstance(resumes, list):
            resumes = []
        resumes.append(
            {
                "worker_id": str(worker_id or ""),
                "ts": _utc_now_iso(),
            }
        )
        task.metadata["resume_events"] = resumes[-20:]
        task.metadata["resumed_by"] = str(worker_id or "")
        task.metadata["resumed_at"] = _utc_now_iso()
        task.updated_at = datetime.now(timezone.utc)
        ok = await self.store.update_task(task)
        RuntimeMetrics.observe("recovery_success_rate", 1.0 if ok else 0.0)
        return ok

    async def mark_terminal(self, task_id: str, status: str, reason: str) -> bool:
        task = await self.store.get_task(task_id)
        if task is None:
            return False
        normalized = str(status or "").strip().upper()
        try:
            task.status = TaskStatus[normalized]
        except Exception:
            # Keep existing status if unknown; still persist terminal reason.
            pass
        task.metadata = task.metadata or {}
        task.metadata["terminal_reason"] = str(reason or "").strip()
        task.metadata["terminal_at"] = _utc_now_iso()
        task.updated_at = datetime.now(timezone.utc)
        if reason and not task.error:
            task.error = str(reason or "").strip()
        return await self.store.update_task(task)


def encode_checkpoint_payload(payload: Dict[str, Any]) -> str:
    return json.dumps(payload or {}, ensure_ascii=True, separators=(",", ":"))
