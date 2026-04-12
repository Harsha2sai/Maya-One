"""
Scheduling Tools Contracts + Runtime Wrappers for Phase 4.

CronCreate, CronDelete, CronList tools for background task scheduling.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from core.agents.scheduling_agent_handler import SchedulingAgentHandler
from core.tasks.task_models import Task, TaskPriority, TaskStatus
from core.tasks.task_store import TaskStore

try:
    from core.tasks.task_persistence import TaskPersistenceManager
except Exception:  # pragma: no cover - fallback for older branches
    TaskPersistenceManager = None

logger = logging.getLogger(__name__)


class CronTrigger(BaseModel):
    """Cron-style scheduling trigger."""
    minute: str = Field(default="0", description="Minute (0-59, */5, etc.)")
    hour: str = Field(default="*", description="Hour (0-23, */2, etc.)")
    day_of_month: str = Field(default="*", description="Day of month (1-31)")
    month: str = Field(default="*", description="Month (1-12)")
    day_of_week: str = Field(default="*", description="Day of week (0-6)")

    def to_cron_expression(self) -> str:
        """Convert to standard cron format."""
        return f"{self.minute} {self.hour} {self.day_of_month} {self.month} {self.day_of_week}"

    @classmethod
    def from_cron_expression(cls, expression: str) -> "CronTrigger":
        """Create a trigger from a 5-field cron expression."""
        parts = [part.strip() for part in str(expression or "").split() if part.strip()]
        if len(parts) != 5:
            raise ValueError("cron expression must have exactly 5 fields")
        trigger = cls(
            minute=parts[0],
            hour=parts[1],
            day_of_month=parts[2],
            month=parts[3],
            day_of_week=parts[4],
        )
        trigger.validate_expression()
        return trigger

    def validate_expression(self) -> None:
        for value, min_v, max_v in (
            (self.minute, 0, 59),
            (self.hour, 0, 23),
            (self.day_of_month, 1, 31),
            (self.month, 1, 12),
            (self.day_of_week, 0, 6),
        ):
            if not self._is_valid_field(value, min_v, max_v):
                raise ValueError(f"invalid cron field '{value}'")

    @staticmethod
    def _is_valid_field(value: str, min_v: int, max_v: int) -> bool:
        token = str(value or "").strip()
        if not token:
            return False
        if token == "*":
            return True
        if token.startswith("*/"):
            step = token[2:]
            return step.isdigit() and int(step) > 0
        for part in token.split(","):
            candidate = part.strip()
            if not candidate:
                return False
            if "-" in candidate:
                start, end = candidate.split("-", 1)
                if not (start.isdigit() and end.isdigit()):
                    return False
                low = int(start)
                high = int(end)
                if low > high or low < min_v or high > max_v:
                    return False
                continue
            if not re.fullmatch(r"\d+", candidate):
                return False
            number = int(candidate)
            if number < min_v or number > max_v:
                return False
        return True

    @staticmethod
    def _field_matches(value: int, expression: str) -> bool:
        token = str(expression or "").strip()
        if token == "*":
            return True
        if token.startswith("*/"):
            step = int(token[2:])
            return step > 0 and value % step == 0
        for part in token.split(","):
            candidate = part.strip()
            if "-" in candidate:
                start, end = candidate.split("-", 1)
                if int(start) <= value <= int(end):
                    return True
            elif candidate.isdigit() and int(candidate) == value:
                return True
        return False

    def matches_datetime(self, dt: datetime) -> bool:
        # Python weekday is Mon=0..Sun=6, cron here uses Sun=0..Sat=6.
        cron_weekday = (dt.weekday() + 1) % 7
        return (
            self._field_matches(dt.minute, self.minute)
            and self._field_matches(dt.hour, self.hour)
            and self._field_matches(dt.day, self.day_of_month)
            and self._field_matches(dt.month, self.month)
            and self._field_matches(cron_weekday, self.day_of_week)
        )

    def next_run_after(self, dt: Optional[datetime] = None) -> Optional[datetime]:
        self.validate_expression()
        start = (dt or datetime.now(timezone.utc)).astimezone(timezone.utc).replace(second=0, microsecond=0)
        probe = start + timedelta(minutes=1)
        for _ in range(60 * 24 * 366):
            if self.matches_datetime(probe):
                return probe
            probe = probe + timedelta(minutes=1)
        return None


class ScheduledTaskStatus(str, Enum):
    """Status of a scheduled task."""
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    ERROR = "error"


class ScheduledTask(BaseModel):
    """A task scheduled via cron."""
    id: str = Field(description="Unique schedule ID")
    task_type: str = Field(description="Type of task to execute")
    trigger: CronTrigger
    params: Dict[str, Any] = Field(default_factory=dict)
    status: ScheduledTaskStatus = ScheduledTaskStatus.ACTIVE
    created_at: datetime = Field(default_factory=datetime.utcnow)
    next_run: Optional[datetime] = None
    last_run: Optional[datetime] = None
    run_count: int = 0
    error_count: int = 0
    user_id: Optional[str] = None
    description: Optional[str] = None


class CronCreateRequest(BaseModel):
    """Request to create a scheduled task."""
    task_type: str = Field(description="Task type to schedule")
    cron_expression: Optional[str] = None
    trigger: Optional[CronTrigger] = None
    params: Dict[str, Any] = Field(default_factory=dict)
    description: Optional[str] = None
    user_id: Optional[str] = None


class CronCreateResult(BaseModel):
    """Result of creating a scheduled task."""
    success: bool
    schedule_id: Optional[str] = None
    next_run: Optional[datetime] = None
    error: Optional[str] = None


class CronDeleteRequest(BaseModel):
    """Request to delete a scheduled task."""
    schedule_id: str


class CronDeleteResult(BaseModel):
    """Result of deleting a scheduled task."""
    success: bool
    deleted_task: Optional[ScheduledTask] = None
    error: Optional[str] = None


class CronListRequest(BaseModel):
    """Request to list scheduled tasks."""
    user_id: Optional[str] = None
    status: Optional[ScheduledTaskStatus] = None
    task_type: Optional[str] = None


class CronListResult(BaseModel):
    """Result of listing scheduled tasks."""
    tasks: List[ScheduledTask] = Field(default_factory=list)
    total_count: int = 0
    active_count: int = 0
    paused_count: int = 0


def _resolve_trigger(trigger: str | CronTrigger) -> CronTrigger:
    if isinstance(trigger, CronTrigger):
        trigger.validate_expression()
        return trigger
    return CronTrigger.from_cron_expression(str(trigger or "").strip())


def _get_persistence() -> Any:
    if TaskPersistenceManager is None:
        return None
    try:
        return TaskPersistenceManager()
    except Exception:
        return None


def _task_status_to_schedule_status(task: Task) -> ScheduledTaskStatus:
    metadata = dict(task.metadata or {})
    schedule_state = str(metadata.get("schedule_status") or "").strip().lower()
    if schedule_state == ScheduledTaskStatus.PAUSED.value:
        return ScheduledTaskStatus.PAUSED

    task_status = str(task.status.value if hasattr(task.status, "value") else task.status).upper()
    if task_status in {"FAILED"}:
        return ScheduledTaskStatus.ERROR
    if task_status in {"CANCELLED", "COMPLETED", "STALE", "PLAN_FAILED"}:
        return ScheduledTaskStatus.COMPLETED
    return ScheduledTaskStatus.ACTIVE


def _task_to_scheduled(task: Task) -> ScheduledTask:
    metadata = dict(task.metadata or {})
    trigger_obj = metadata.get("trigger") if isinstance(metadata.get("trigger"), dict) else {}
    trigger = CronTrigger(**trigger_obj) if trigger_obj else CronTrigger()

    def _parse_dt(value: Any) -> Optional[datetime]:
        if not value:
            return None
        try:
            return datetime.fromisoformat(str(value))
        except Exception:
            return None

    return ScheduledTask(
        id=str(task.id),
        task_type=str(metadata.get("task_type") or task.title or "scheduled_task"),
        trigger=trigger,
        params=dict(metadata.get("payload") or {}),
        status=_task_status_to_schedule_status(task),
        created_at=task.created_at,
        next_run=_parse_dt(metadata.get("next_run")),
        last_run=_parse_dt(metadata.get("last_run")),
        run_count=int(metadata.get("run_count") or 0),
        error_count=int(metadata.get("error_count") or 0),
        user_id=str(task.user_id or "") or None,
        description=task.description,
    )


async def create_scheduled_task(
    task_type: str,
    payload: Dict[str, Any],
    trigger: str | CronTrigger,
    *,
    user_id: str = "system",
) -> CronCreateResult:
    """Create a persistent scheduled task wrapper and checkpoint it."""
    normalized_type = str(task_type or "").strip().lower()
    if not normalized_type:
        return CronCreateResult(success=False, error="task_type is required")

    handler = SchedulingAgentHandler()
    if normalized_type not in handler.SCHEDULING_INTENTS:
        return CronCreateResult(success=False, error=f"unsupported scheduling task_type: {normalized_type}")

    try:
        resolved_trigger = _resolve_trigger(trigger)
    except Exception as exc:
        return CronCreateResult(success=False, error=f"invalid trigger: {exc}")

    next_run = resolved_trigger.next_run_after(datetime.now(timezone.utc))
    metadata = {
        "scheduled_task": True,
        "task_type": normalized_type,
        "trigger": resolved_trigger.model_dump(),
        "cron_expression": resolved_trigger.to_cron_expression(),
        "payload": dict(payload or {}),
        "next_run": next_run.isoformat() if next_run else None,
        "schedule_status": ScheduledTaskStatus.ACTIVE.value,
        "created_via": "core.tools.scheduling",
    }

    task = Task(
        user_id=str(user_id or "system"),
        title=f"Scheduled: {normalized_type}",
        description=f"Scheduled task for {normalized_type}",
        status=TaskStatus.WAITING,
        priority=TaskPriority.MEDIUM,
        metadata=metadata,
    )
    if hasattr(task, "persistent"):
        setattr(task, "persistent", True)
    if hasattr(task, "cron_expression"):
        setattr(task, "cron_expression", resolved_trigger.to_cron_expression())
    if hasattr(task, "background_mode"):
        setattr(task, "background_mode", True)

    store = TaskStore()
    created = await store.create_task(task)
    if not created:
        return CronCreateResult(success=False, error="failed to persist scheduled task")

    persistence = _get_persistence()
    if persistence is not None:
        try:
            await persistence.save_checkpoint(
                task_id=task.id,
                step_id="schedule_create",
                payload={
                    "event": "scheduled_task_created",
                    "task_id": task.id,
                    "task_type": normalized_type,
                    "trigger": resolved_trigger.to_cron_expression(),
                    "payload": dict(payload or {}),
                    "next_run": metadata["next_run"],
                },
            )
        except Exception as exc:
            logger.warning("scheduled_task_checkpoint_failed task_id=%s error=%s", task.id, exc)

    return CronCreateResult(
        success=True,
        schedule_id=task.id,
        next_run=next_run,
    )


async def list_scheduled_tasks(user_id: str) -> CronListResult:
    """List persistent scheduled tasks for a user from TaskStore."""
    store = TaskStore()
    tasks = await store.list_tasks(str(user_id or ""), limit=500)
    scheduled: List[ScheduledTask] = []

    for task in tasks:
        metadata = dict(task.metadata or {})
        if bool(metadata.get("scheduled_task")) or bool(getattr(task, "persistent", False)):
            try:
                scheduled.append(_task_to_scheduled(task))
            except Exception as exc:
                logger.warning("scheduled_task_decode_failed task_id=%s error=%s", task.id, exc)

    active_count = sum(1 for item in scheduled if item.status == ScheduledTaskStatus.ACTIVE)
    paused_count = sum(1 for item in scheduled if item.status == ScheduledTaskStatus.PAUSED)
    return CronListResult(
        tasks=scheduled,
        total_count=len(scheduled),
        active_count=active_count,
        paused_count=paused_count,
    )


async def cancel_scheduled_task(task_id: str) -> CronDeleteResult:
    """Cancel a scheduled task and mark it terminal in TaskStore/persistence."""
    normalized_id = str(task_id or "").strip()
    if not normalized_id:
        return CronDeleteResult(success=False, error="schedule_id is required")

    store = TaskStore()
    task = await store.get_task(normalized_id)
    if task is None:
        return CronDeleteResult(success=False, error=f"scheduled task not found: {normalized_id}")

    metadata = dict(task.metadata or {})
    if not bool(metadata.get("scheduled_task")) and not bool(getattr(task, "persistent", False)):
        return CronDeleteResult(success=False, error=f"task is not a scheduled task: {normalized_id}")

    metadata["schedule_status"] = "cancelled"
    metadata["cancelled_at"] = datetime.now(timezone.utc).isoformat()
    task.metadata = metadata
    task.status = TaskStatus.CANCELLED
    task.error = "scheduled_task_cancelled"

    updated = await store.update_task(task)
    if not updated:
        return CronDeleteResult(success=False, error=f"failed to cancel scheduled task: {normalized_id}")

    persistence = _get_persistence()
    if persistence is not None:
        try:
            await persistence.mark_terminal(
                task_id=normalized_id,
                status="CANCELLED",
                reason="scheduled_task_cancelled",
            )
        except Exception as exc:
            logger.warning("scheduled_task_mark_terminal_failed task_id=%s error=%s", normalized_id, exc)

    return CronDeleteResult(success=True, deleted_task=_task_to_scheduled(task))


async def cron_create(request: CronCreateRequest) -> CronCreateResult:
    """Tool-style wrapper for scheduled task creation."""
    trigger: str | CronTrigger
    if request.trigger is not None:
        trigger = request.trigger
    elif request.cron_expression:
        trigger = request.cron_expression
    else:
        return CronCreateResult(success=False, error="trigger or cron_expression is required")
    return await create_scheduled_task(
        task_type=request.task_type,
        payload=request.params,
        trigger=trigger,
        user_id=str(request.user_id or "system"),
    )


async def cron_delete(request: CronDeleteRequest) -> CronDeleteResult:
    """Tool-style wrapper for scheduled task deletion."""
    return await cancel_scheduled_task(request.schedule_id)


async def cron_list(request: CronListRequest) -> CronListResult:
    """Tool-style wrapper for scheduled task listing."""
    result = await list_scheduled_tasks(str(request.user_id or ""))
    if request.status is None and request.task_type is None:
        return result

    filtered: List[ScheduledTask] = []
    for item in result.tasks:
        if request.status is not None and item.status != request.status:
            continue
        if request.task_type is not None and item.task_type != request.task_type:
            continue
        filtered.append(item)

    return CronListResult(
        tasks=filtered,
        total_count=len(filtered),
        active_count=sum(1 for item in filtered if item.status == ScheduledTaskStatus.ACTIVE),
        paused_count=sum(1 for item in filtered if item.status == ScheduledTaskStatus.PAUSED),
    )
