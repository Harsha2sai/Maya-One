"""Cron-style scheduler wrapper for background executor tasks."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .executor import BackgroundExecutor

try:  # pragma: no cover - availability depends on runtime env
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.cron import CronTrigger
except Exception:  # pragma: no cover - exercised by tests with missing dependency
    AsyncIOScheduler = None
    CronTrigger = None


@dataclass
class ScheduledJob:
    job_id: str
    task_id: str
    task_type: str
    cron_expression: str
    payload: Dict[str, Any] = field(default_factory=dict)
    recoverable: bool = True
    next_run_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "task_id": self.task_id,
            "task_type": self.task_type,
            "cron_expression": self.cron_expression,
            "payload": dict(self.payload or {}),
            "recoverable": bool(self.recoverable),
            "next_run_at": self.next_run_at.isoformat() if self.next_run_at else None,
        }


class TaskScheduler:
    """Schedules recurring background jobs and dispatches to BackgroundExecutor."""

    def __init__(self, *, executor: BackgroundExecutor, timezone_name: str = "UTC") -> None:
        self._executor = executor
        self._jobs: Dict[str, ScheduledJob] = {}
        self._timezone = timezone_name
        self._scheduler = None
        self._started = False

        if AsyncIOScheduler is not None:
            self._scheduler = AsyncIOScheduler(timezone=timezone_name)

    @property
    def available(self) -> bool:
        return self._scheduler is not None and CronTrigger is not None

    @property
    def started(self) -> bool:
        return self._started

    async def start(self) -> None:
        if self._started:
            return
        if self._scheduler is not None:
            self._scheduler.start()
        self._started = True

    async def shutdown(self) -> None:
        if not self._started:
            return
        if self._scheduler is not None:
            self._scheduler.shutdown(wait=False)
        self._started = False

    def add_cron_task(
        self,
        *,
        job_id: str,
        task_id: str,
        task_type: str,
        cron_expression: str,
        payload: Optional[Dict[str, Any]] = None,
        recoverable: bool = True,
    ) -> ScheduledJob:
        resolved_job_id = str(job_id or "").strip()
        if not resolved_job_id:
            raise ValueError("job_id is required")

        resolved_task_id = str(task_id or "").strip()
        if not resolved_task_id:
            raise ValueError("task_id is required")

        resolved_task_type = str(task_type or "").strip().lower()
        if not resolved_task_type:
            raise ValueError("task_type is required")

        normalized_cron = self._normalize_cron(cron_expression)

        job = ScheduledJob(
            job_id=resolved_job_id,
            task_id=resolved_task_id,
            task_type=resolved_task_type,
            cron_expression=normalized_cron,
            payload=dict(payload or {}),
            recoverable=bool(recoverable),
            next_run_at=None,
        )

        if self._scheduler is not None and CronTrigger is not None:
            trigger = CronTrigger.from_crontab(normalized_cron, timezone=self._timezone)
            aps_job = self._scheduler.add_job(
                self._dispatch_job,
                trigger=trigger,
                id=resolved_job_id,
                replace_existing=True,
                kwargs={"job_id": resolved_job_id},
            )
            job.next_run_at = aps_job.next_run_time

        self._jobs[resolved_job_id] = job
        return job

    def remove_task(self, job_id: str) -> bool:
        resolved_job_id = str(job_id or "").strip()
        if not resolved_job_id:
            return False

        existed = resolved_job_id in self._jobs
        self._jobs.pop(resolved_job_id, None)
        if self._scheduler is not None:
            try:
                self._scheduler.remove_job(resolved_job_id)
            except Exception:
                pass
        return existed

    def list_tasks(self) -> List[Dict[str, Any]]:
        return [job.to_dict() for job in self._jobs.values()]

    async def run_due_job(self, job_id: str) -> Dict[str, Any]:
        return await self._dispatch_job(job_id=job_id)

    async def _dispatch_job(self, *, job_id: str) -> Dict[str, Any]:
        job = self._jobs.get(str(job_id or "").strip())
        if job is None:
            raise LookupError(f"scheduled_job_not_found:{job_id}")

        result = await self._executor.submit(
            task_id=job.task_id,
            task_type=job.task_type,
            payload=dict(job.payload),
            task_ref=f"{job.job_id}:{int(datetime.now(timezone.utc).timestamp())}",
            recoverable=job.recoverable,
            metadata={
                "scheduled_task": True,
                "job_id": job.job_id,
                "task_type": job.task_type,
                "payload": dict(job.payload),
                "recoverable": bool(job.recoverable),
            },
        )
        return result

    @staticmethod
    def _normalize_cron(cron_expression: str) -> str:
        normalized = " ".join(str(cron_expression or "").split())
        parts = normalized.split(" ")
        if len(parts) != 5:
            raise ValueError("cron expression must have 5 fields")
        return normalized
