
import logging
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple
from enum import Enum

from core.tasks.task_models import Task, TaskStatus
from core.tasks.task_steps import TaskStep, TaskStepStatus
from core.tasks.task_store import TaskStore

logger = logging.getLogger(__name__)


class TaskStateMachine:
    VALID_TRANSITIONS = {
        TaskStatus.PENDING: {TaskStatus.RUNNING, TaskStatus.CANCELLED},
        TaskStatus.PLANNING: {
            TaskStatus.PENDING,
            TaskStatus.RUNNING,
            TaskStatus.FAILED,
            TaskStatus.PLAN_FAILED,
        },
        TaskStatus.RUNNING: {
            TaskStatus.COMPLETED,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
            TaskStatus.WAITING,
            TaskStatus.STALE,
        },
        TaskStatus.WAITING: {
            TaskStatus.RUNNING,
            TaskStatus.COMPLETED,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
            TaskStatus.STALE,
        },
        TaskStatus.PLAN_FAILED: set(),
        TaskStatus.STALE: set(),
        TaskStatus.COMPLETED: set(),
        TaskStatus.FAILED: set(),
        TaskStatus.CANCELLED: set(),
    }

    STEP_VALID_TRANSITIONS = {
        TaskStepStatus.PENDING: {TaskStepStatus.RUNNING, TaskStepStatus.FAILED},
        TaskStepStatus.RUNNING: {TaskStepStatus.DONE, TaskStepStatus.FAILED, TaskStepStatus.PENDING},
        TaskStepStatus.DONE: set(),
        TaskStepStatus.FAILED: set(),
    }

    @classmethod
    def can_transition(cls, from_status: TaskStatus, to_status: TaskStatus) -> bool:
        return to_status in cls.VALID_TRANSITIONS.get(from_status, set())

    @classmethod
    def can_step_transition(cls, from_status: TaskStepStatus, to_status: TaskStepStatus) -> bool:
        return to_status in cls.STEP_VALID_TRANSITIONS.get(from_status, set())


class AtomicTaskStore:
    LEASE_SECONDS = 300
    STALE_TASK_SECONDS = 600

    def __init__(self, store: TaskStore):
        self.store = store

    async def claim_task(self, task_id: str, worker_id: str) -> Optional[Task]:
        task = await self.store.get_task(task_id)
        if not task:
            logger.warning(f"Task {task_id} not found for claim")
            return None

        if task.status != TaskStatus.PENDING:
            logger.warning(f"Task {task_id} not in PENDING state (current: {task.status}), cannot claim")
            return None

        task.status = TaskStatus.RUNNING
        task.metadata = task.metadata or {}
        task.metadata["claimed_by"] = worker_id
        task.metadata["claimed_at"] = datetime.now(timezone.utc).isoformat()
        task.metadata["lease_expires_at"] = (
            datetime.now(timezone.utc) + timedelta(seconds=self.LEASE_SECONDS)
        ).isoformat()

        if await self.store.update_task(task):
            logger.info(f"Task {task_id} claimed by worker {worker_id}")
            return task

        logger.error(f"Failed to claim task {task_id}")
        return None

    async def claim_task_if_stale(self, task_id: str, worker_id: str) -> Optional[Task]:
        task = await self.store.get_task(task_id)
        if not task:
            return None

        if task.status != TaskStatus.RUNNING:
            return None

        lease_expires = task.metadata.get("lease_expires_at") if task.metadata else None
        if not lease_expires:
            # Legacy/unclaimed running task: take ownership.
            task.metadata = task.metadata or {}
            task.metadata["claimed_by"] = worker_id
            task.metadata["lease_renewed_at"] = datetime.now(timezone.utc).isoformat()
            task.metadata["lease_expires_at"] = (
                datetime.now(timezone.utc) + timedelta(seconds=self.LEASE_SECONDS)
            ).isoformat()
            if await self.store.update_task(task):
                logger.info(f"Task {task_id} claimed by worker {worker_id} (running/unclaimed)")
                return task
            return None

        try:
            lease_time = datetime.fromisoformat(lease_expires)
            if lease_time > datetime.now(timezone.utc):
                return None
        except (ValueError, TypeError):
            pass

        task.metadata = task.metadata or {}
        task.metadata["claimed_by"] = worker_id
        task.metadata["lease_renewed_at"] = datetime.now(timezone.utc).isoformat()
        task.metadata["lease_expires_at"] = (
            datetime.now(timezone.utc) + timedelta(seconds=self.LEASE_SECONDS)
        ).isoformat()

        if await self.store.update_task(task):
            logger.info(f"Task {task_id} re-claimed by worker {worker_id} (stale)")
            return task

        return None

    async def claim_or_renew(self, task_id: str, worker_id: str) -> Optional[Task]:
        """
        Claim pending tasks, renew leases for owned running tasks, or reclaim stale/unowned tasks.
        """
        task = await self.store.get_task(task_id)
        if not task:
            return None

        if task.status == TaskStatus.PENDING:
            return await self.claim_task(task_id, worker_id)

        if task.status != TaskStatus.RUNNING:
            return None

        metadata = task.metadata or {}
        claimed_by = metadata.get("claimed_by")
        if claimed_by == worker_id:
            ok = await self.heartbeat(task_id, worker_id)
            return await self.store.get_task(task_id) if ok else None

        # Reclaim stale or unowned running tasks.
        return await self.claim_task_if_stale(task_id, worker_id)

    async def update_step_status(
        self,
        task_id: str,
        step_index: int,
        new_status: TaskStepStatus,
        result: Optional[str] = None,
        error: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> Tuple[bool, Optional[Task]]:
        task = await self.store.get_task(task_id)
        if not task:
            return False, None

        if step_index >= len(task.steps):
            logger.error(f"Step index {step_index} out of bounds for task {task_id}")
            return False, None

        step = task.steps[step_index]

        if step.status == new_status:
            # Idempotent no-op transition.
            return True, task

        if idempotency_key:
            existing_key = step.metadata.get("last_idempotency_key") if step.metadata else None
            if existing_key == idempotency_key:
                logger.debug(f"Step {step_index} already processed with idempotency key {idempotency_key}")
                return True, task

        if not TaskStateMachine.can_step_transition(step.status, new_status):
            logger.warning(
                f"Invalid step transition {step.status} -> {new_status} for step {step_index}"
            )
            return False, None

        old_status = step.status
        step.status = new_status
        step.result = result or step.result
        step.error = error

        if new_status == TaskStepStatus.DONE:
            step.completed_at = datetime.now(timezone.utc)

        if idempotency_key:
            step.metadata = step.metadata or {}
            step.metadata["last_idempotency_key"] = idempotency_key

        if await self.store.update_task(task):
            logger.info(f"Step {step_index} transitioned {old_status} -> {new_status} for task {task_id}")
            return True, task

        return False, None

    async def heartbeat(self, task_id: str, worker_id: str) -> bool:
        task = await self.store.get_task(task_id)
        if not task:
            return False

        if task.status != TaskStatus.RUNNING:
            return False

        claimed_by = task.metadata.get("claimed_by") if task.metadata else None
        if claimed_by != worker_id:
            logger.warning(f"Task {task_id} claimed by {claimed_by}, cannot heartbeat from {worker_id}")
            return False

        task.metadata = task.metadata or {}
        task.metadata["last_heartbeat"] = datetime.now(timezone.utc).isoformat()
        task.metadata["lease_expires_at"] = (
            datetime.now(timezone.utc) + timedelta(seconds=self.LEASE_SECONDS)
        ).isoformat()

        return await self.store.update_task(task)

    async def find_stale_tasks(self) -> list[Task]:
        all_tasks = await self.store.list_tasks(user_id="", limit=1000)
        stale = []
        now = datetime.now(timezone.utc)

        for task in all_tasks:
            if task.status != TaskStatus.RUNNING:
                continue

            lease_expires = task.metadata.get("lease_expires_at") if task.metadata else None
            if not lease_expires:
                continue

            try:
                lease_time = datetime.fromisoformat(lease_expires)
                if lease_time < now:
                    stale.append(task)
            except (ValueError, TypeError):
                continue

        return stale

    async def release_task(self, task_id: str) -> bool:
        task = await self.store.get_task(task_id)
        if not task:
            return False

        if task.status == TaskStatus.RUNNING:
            task.status = TaskStatus.PENDING
            task.metadata = task.metadata or {}
            task.metadata.pop("claimed_by", None)
            task.metadata.pop("lease_expires_at", None)

            return await self.store.update_task(task)

        return False
