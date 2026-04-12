"""Team mode coordinator for parallel delegation and deterministic reduction."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable, Dict, Iterable, List, Sequence

from .review import ReviewReducer, ReviewSeverity


class TeamTaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


@dataclass
class TeamTask:
    task_id: str
    agent_name: str
    payload: Dict[str, Any] = field(default_factory=dict)
    timeout_s: float | None = None


@dataclass
class TeamExecution:
    task_id: str
    agent_name: str
    status: TeamTaskStatus
    result: Any = None
    error: str | None = None
    started_at: float = 0.0
    ended_at: float = 0.0

    @property
    def duration_ms(self) -> int:
        if self.ended_at <= self.started_at:
            return 0
        return int((self.ended_at - self.started_at) * 1000.0)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "agent_name": self.agent_name,
            "status": self.status.value,
            "result": self.result,
            "error": self.error,
            "duration_ms": self.duration_ms,
        }


TeamHandler = Callable[[Dict[str, Any]], Awaitable[Any] | Any]


class TeamCoordinator:
    """Coordinates parallel agent tasks and reduces outputs into one decision."""

    def __init__(
        self,
        *,
        max_parallel: int = 4,
        review_reducer: ReviewReducer | None = None,
    ) -> None:
        self.max_parallel = max(1, int(max_parallel))
        self._handlers: Dict[str, TeamHandler] = {}
        self._review_reducer = review_reducer or ReviewReducer()

    def register_agent(self, agent_name: str, handler: TeamHandler) -> None:
        normalized_name = str(agent_name or "").strip().lower()
        if not normalized_name:
            raise ValueError("agent_name is required")
        if not callable(handler):
            raise TypeError("handler must be callable")
        self._handlers[normalized_name] = handler

    def unregister_agent(self, agent_name: str) -> None:
        normalized_name = str(agent_name or "").strip().lower()
        self._handlers.pop(normalized_name, None)

    def list_agents(self) -> List[str]:
        return sorted(self._handlers.keys())

    async def run_task(self, task: TeamTask) -> TeamExecution:
        started = time.monotonic()
        handler = self._handlers.get(str(task.agent_name or "").strip().lower())
        if handler is None:
            ended = time.monotonic()
            return TeamExecution(
                task_id=task.task_id,
                agent_name=task.agent_name,
                status=TeamTaskStatus.FAILED,
                error=f"unregistered_agent:{task.agent_name}",
                started_at=started,
                ended_at=ended,
            )

        async def _invoke() -> Any:
            maybe = handler(dict(task.payload or {}))
            if asyncio.iscoroutine(maybe):
                return await maybe
            return maybe

        try:
            if task.timeout_s is not None and float(task.timeout_s) > 0:
                result = await asyncio.wait_for(_invoke(), timeout=float(task.timeout_s))
            else:
                result = await _invoke()
            ended = time.monotonic()
            return TeamExecution(
                task_id=task.task_id,
                agent_name=task.agent_name,
                status=TeamTaskStatus.COMPLETED,
                result=result,
                started_at=started,
                ended_at=ended,
            )
        except asyncio.TimeoutError:
            ended = time.monotonic()
            return TeamExecution(
                task_id=task.task_id,
                agent_name=task.agent_name,
                status=TeamTaskStatus.TIMEOUT,
                error="task_timeout",
                started_at=started,
                ended_at=ended,
            )
        except asyncio.CancelledError:
            ended = time.monotonic()
            return TeamExecution(
                task_id=task.task_id,
                agent_name=task.agent_name,
                status=TeamTaskStatus.CANCELLED,
                error="task_cancelled",
                started_at=started,
                ended_at=ended,
            )
        except Exception as exc:  # pragma: no cover - depends on handler behavior
            ended = time.monotonic()
            return TeamExecution(
                task_id=task.task_id,
                agent_name=task.agent_name,
                status=TeamTaskStatus.FAILED,
                error=str(exc),
                started_at=started,
                ended_at=ended,
            )

    async def run_batch(
        self,
        tasks: Sequence[TeamTask],
        *,
        fail_fast: bool = False,
    ) -> List[TeamExecution]:
        semaphore = asyncio.Semaphore(self.max_parallel)
        stop_event = asyncio.Event()
        executions: List[TeamExecution] = []

        async def _worker(item: TeamTask) -> TeamExecution:
            if fail_fast and stop_event.is_set():
                now = time.monotonic()
                return TeamExecution(
                    task_id=item.task_id,
                    agent_name=item.agent_name,
                    status=TeamTaskStatus.CANCELLED,
                    error="cancelled_due_to_fail_fast",
                    started_at=now,
                    ended_at=now,
                )

            async with semaphore:
                if fail_fast and stop_event.is_set():
                    now = time.monotonic()
                    return TeamExecution(
                        task_id=item.task_id,
                        agent_name=item.agent_name,
                        status=TeamTaskStatus.CANCELLED,
                        error="cancelled_due_to_fail_fast",
                        started_at=now,
                        ended_at=now,
                    )

                execution = await self.run_task(item)
                if fail_fast and execution.status in {TeamTaskStatus.FAILED, TeamTaskStatus.TIMEOUT}:
                    stop_event.set()
                return execution

        executions = await asyncio.gather(*[_worker(task) for task in tasks])
        return list(executions)

    def reduce_results(self, executions: Sequence[TeamExecution], *, strategy: str = "first_success") -> Dict[str, Any]:
        normalized_strategy = str(strategy or "first_success").strip().lower()
        completed = [item for item in executions if item.status == TeamTaskStatus.COMPLETED]
        failed = [item for item in executions if item.status != TeamTaskStatus.COMPLETED]

        if normalized_strategy == "first_success":
            if completed:
                winner = completed[0]
                return {
                    "success": True,
                    "strategy": normalized_strategy,
                    "winner": winner.to_dict(),
                    "executions": [item.to_dict() for item in executions],
                }
            return {
                "success": False,
                "strategy": normalized_strategy,
                "error": "no_successful_results",
                "failed": [item.to_dict() for item in failed],
                "executions": [item.to_dict() for item in executions],
            }

        if normalized_strategy == "all_success":
            return {
                "success": len(failed) == 0,
                "strategy": normalized_strategy,
                "executions": [item.to_dict() for item in executions],
                "failed_count": len(failed),
            }

        if normalized_strategy == "merge_dict":
            merged: Dict[str, Any] = {}
            for item in completed:
                if isinstance(item.result, dict):
                    merged.update(item.result)
            return {
                "success": True,
                "strategy": normalized_strategy,
                "merged": merged,
                "executions": [item.to_dict() for item in executions],
            }

        if normalized_strategy == "review":
            findings: List[Any] = []
            for item in completed:
                if isinstance(item.result, dict) and isinstance(item.result.get("findings"), list):
                    findings.extend(item.result.get("findings") or [])
            summary = self._review_reducer.summarize(findings, threshold=ReviewSeverity.ERROR)
            return {
                "success": not summary.should_block,
                "strategy": normalized_strategy,
                "review": {
                    "total": summary.total,
                    "counts": summary.counts,
                    "highest_severity": summary.highest_severity,
                    "should_block": summary.should_block,
                },
                "executions": [item.to_dict() for item in executions],
            }

        raise ValueError(f"unsupported reduction strategy: {normalized_strategy}")

    async def coordinate(
        self,
        tasks: Sequence[TeamTask],
        *,
        strategy: str = "first_success",
        fail_fast: bool = False,
    ) -> Dict[str, Any]:
        executions = await self.run_batch(tasks, fail_fast=fail_fast)
        return self.reduce_results(executions, strategy=strategy)
