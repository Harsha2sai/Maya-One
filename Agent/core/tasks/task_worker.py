import logging
import asyncio
from typing import Any, Dict, Optional, Callable, Awaitable
from datetime import datetime, timezone, timedelta
import uuid
import time

from core.tasks.task_models import Task, TaskStatus
from core.tasks.task_manager import TaskManager
from core.tasks.workers.registry import WorkerRegistry
from core.tasks.task_steps import TaskStepStatus, WorkerType
from core.tasks.task_limits import MAX_STEPS_PER_TASK, MAX_TASK_RUNTIME_SECONDS
from core.tasks.atomic_task_state import AtomicTaskStore
from core.telemetry.runtime_metrics import RuntimeMetrics
import pytz
from core.utils.intent_utils import normalize_intent
from core.observability.trace_context import set_trace_context
from core.tasks.execution_evaluator import ExecutionEvaluator, ExecutionContext
from core.tasks.step_controller import StepController

logger = logging.getLogger(__name__)

STEP_TIMEOUT_SECONDS = 120
STEP_MAX_RETRIES = 3
STUCK_TASK_THRESHOLD_SECONDS = 600
RECENT_RUNNING_STALE_WINDOW_SECONDS = 60


class _NoopMemoryManager:
    """Fallback memory sink for tests/dev scripts that don't inject memory."""

    def store_tool_output(self, **_kwargs):
        return None

    def store_task_result(self, **_kwargs):
        return None


class TaskWorker:
    """
    Background worker that acts as a DISPATCHER.
    It fetches active tasks and dispatches steps to Specialist Workers.
    """
    def __init__(
        self,
        user_id: str,
        interval: float = 2.0,
        memory_manager: Any = None,
        smart_llm: Any = None,
        room: Any = None,
        event_notifier: Optional[Callable[[Dict[str, Any]], Any]] = None,
    ):
        self.user_id = user_id
        self.interval = interval
        effective_memory = memory_manager if memory_manager is not None else _NoopMemoryManager()
        self.manager = TaskManager(user_id, effective_memory)
        self.atomic_store = AtomicTaskStore(self.manager.store)
        self.worker_id = f"worker:{self.user_id}:{str(uuid.uuid4())[:8]}"
        self.room = room
        self.registry = WorkerRegistry(
            user_id,
            self.manager.store,
            self.manager.memory,
            smart_llm,
            room=self.room,
        )
        self._running = False
        self._task = None
        self._shutdown_event = asyncio.Event()
        self._event_notifier = event_notifier
        self._evaluator = ExecutionEvaluator()
        self._step_controller = StepController(
            tool_executor=self._execute_tool,
            evaluator=self._evaluator,
        )

    @property
    def is_running(self) -> bool:
        return self._running and self._task is not None and not self._task.done()

    def set_room(self, room: Any) -> None:
        self.room = room
        self.registry.update_room(room)

    async def _execute_tool(self, tool: str, parameters: Dict[str, Any]) -> str:
        """Execute a single tool with parameters. Used by StepController."""
        try:
            worker = self.registry.get_worker(WorkerType.GENERAL)
            result = await worker.execute_tool(tool, parameters)
            return str(result) if result is not None else ""
        except Exception as e:
            logger.error(f"Tool execution failed: {tool} error={e}")
            raise

    def _log_execution_event(
        self,
        *,
        task: Task,
        tool_name: str,
        latency_ms: float,
        outcome: str,
    ) -> None:
        logger.info(
            "worker_execution_event",
            extra={
                "trace_id": (task.metadata or {}).get("trace_id"),
                "session_id": (task.metadata or {}).get("session_id"),
                "user_id": self.user_id,
                "task_id": task.id,
                "tool_name": tool_name or "reasoning",
                "latency_ms": latency_ms,
                "outcome": outcome,
            },
        )

    async def start(self):
        """Start the worker loop."""
        if self._running:
            return
        self._running = True
        self._shutdown_event.clear()
        self._task = asyncio.create_task(self._worker_loop())
        self._task.add_done_callback(self._log_background_task_exception)
        logger.info(f"🚀 Task Dispatcher started for user {self.user_id}")

    @staticmethod
    def _log_background_task_exception(task: asyncio.Task) -> None:
        if task.cancelled():
            return
        try:
            error = task.exception()
        except Exception as e:
            logger.error("unhandled_task_exception", extra={"error": str(e)})
            return
        if error:
            logger.error("unhandled_task_exception", extra={"error": str(error)})

    async def stop(self):
        """Stop the worker loop gracefully."""
        logger.info("🛑 Initiating graceful shutdown...")
        self._running = False
        self._shutdown_event.set()
        
        if self._task:
            self._task.cancel()
            try:
                await asyncio.wait_for(self._task, timeout=5.0)
            except asyncio.CancelledError:
                pass
            except asyncio.TimeoutError:
                logger.warning("⚠️ Worker shutdown timed out, forcing cancel")
                self._task.cancel()
        
        logger.info("🛑 Task Dispatcher stopped")

    async def _worker_loop(self):
        while self._running:
            try:
                await self._process_active_tasks()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in task dispatcher loop: {e}", exc_info=True)
            
            await asyncio.sleep(self.interval)
        
        logger.info("Worker loop exited")

    async def _process_active_tasks(self):
        """Fetch and process all active tasks."""
        active_tasks = await self.manager.get_active_tasks()
        logger.debug(f"Worker {self.user_id} found {len(active_tasks)} active tasks")

        actionable = [
            t for t in active_tasks
            if t.status in {TaskStatus.PENDING, TaskStatus.RUNNING, TaskStatus.WAITING, TaskStatus.PLAN_FAILED}
        ]

        for task in actionable:
            try:
                await self._process_single_task(task)
            except Exception as e:
                logger.error(f"❌ Error processing task {task.id}: {e}", exc_info=True)
                continue

    async def _process_single_task(self, task: Task):
        """Process a single task with safety checks."""
        if task.status == TaskStatus.PLAN_FAILED:
            await self._emit_event(
                event_type="plan_failed",
                task=task,
                message="I wasn't able to plan that task.",
            )
            return

        if await self._should_mark_recent_running_stale(task):
            await self._mark_task_stale(
                task=task,
                reason=f"running task updated within {RECENT_RUNNING_STALE_WINDOW_SECONDS}s on worker restart",
            )
            return

        leased_task = await self.atomic_store.claim_or_renew(task.id, self.worker_id)
        if leased_task is None:
            logger.debug(f"Skipping task {task.id}: could not acquire lease for {self.worker_id}")
            return

        task = leased_task
        set_trace_context(
            user_id=self.user_id,
            task_id=task.id,
            session_id=(task.metadata or {}).get("session_id") or "task_worker",
            trace_id=(task.metadata or {}).get("trace_id"),
        )

        if task.status == TaskStatus.WAITING:
            task.status = TaskStatus.RUNNING
            await self.manager.store.update_task(task)

        if task.current_step_index >= MAX_STEPS_PER_TASK:
            logger.warning(f"⛔ Task {task.id} exceeded max steps ({MAX_STEPS_PER_TASK}). Terminating.")
            await self.manager.fail_task(task.id, f"Terminated: Exceeded maximum step limit ({MAX_STEPS_PER_TASK}).")
            return

        now = datetime.now(pytz.UTC)
        start_time = task.created_at
        if start_time.tzinfo is None:
            start_time = start_time.replace(tzinfo=pytz.UTC)
        
        elapsed = (now - start_time).total_seconds()
        
        if elapsed > MAX_TASK_RUNTIME_SECONDS:
            logger.warning(f"⛔ Task {task.id} timed out (runtime: {elapsed}s). Terminating.")
            await self.manager.fail_task(task.id, f"Terminated: Exceeded maximum runtime ({MAX_TASK_RUNTIME_SECONDS}s).")
            RuntimeMetrics.increment("tasks_failed_total")
            return

        if await self._is_task_stuck(task):
            logger.warning(f"⛔ Task {task.id} appears stuck. Attempting recovery.")
            await self._recover_stuck_task(task)
            return

        if task.current_step_index < len(task.steps):
            heartbeat_ok = await self.atomic_store.heartbeat(task.id, self.worker_id)
            if not heartbeat_ok:
                logger.warning(f"⚠️ Task {task.id} lease heartbeat failed. Skipping this cycle.")
                return
            await self._execute_next_step(task)
        else:
            if task.status != TaskStatus.COMPLETED:
                logger.info(f"Task {task.id} all steps processed. Completing.")
                await self.manager.complete_task(task.id, "All steps executed.")
                RuntimeMetrics.increment("tasks_completed_total")
                RuntimeMetrics.observe("task_runtime_seconds", elapsed)

    async def _emit_event(self, *, event_type: str, task: Task, message: str) -> None:
        if not callable(self._event_notifier):
            return
        payload = {
            "event_type": event_type,
            "task_id": task.id,
            "trace_id": (task.metadata or {}).get("trace_id"),
            "session_id": (task.metadata or {}).get("session_id"),
            "message": message,
            "voice_text": message,
        }
        try:
            maybe = self._event_notifier(payload)
            if asyncio.iscoroutine(maybe):
                await maybe
        except Exception as e:
            logger.warning("task_event_emit_failed task_id=%s event_type=%s error=%s", task.id, event_type, e)

    @staticmethod
    def _coerce_datetime(value: Any) -> Optional[datetime]:
        if isinstance(value, datetime):
            return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        if isinstance(value, str):
            try:
                parsed = datetime.fromisoformat(value)
                return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
            except Exception:
                return None
        return None

    async def _should_mark_recent_running_stale(self, task: Task) -> bool:
        if task.status != TaskStatus.RUNNING:
            return False
        metadata = task.metadata or {}
        claimed_by = str(metadata.get("claimed_by") or "").strip()
        if not claimed_by or claimed_by == self.worker_id:
            return False
        updated = self._coerce_datetime(getattr(task, "updated_at", None))
        if not updated:
            return False
        age_seconds = (datetime.now(timezone.utc) - updated).total_seconds()
        return age_seconds < RECENT_RUNNING_STALE_WINDOW_SECONDS

    async def _mark_task_stale(self, *, task: Task, reason: str) -> None:
        task.status = TaskStatus.STALE
        task.error = reason
        task.metadata = task.metadata or {}
        task.metadata["stale_reason"] = reason
        task.metadata["stale_marked_at"] = datetime.now(timezone.utc).isoformat()
        task.metadata.pop("claimed_by", None)
        task.metadata.pop("lease_expires_at", None)
        task.metadata.pop("last_heartbeat", None)
        await self.manager.store.update_task(task)
        await self.manager.store.add_log(task.id, f"Task marked STALE: {reason}")
        await self._emit_event(
            event_type="task_stale",
            task=task,
            message="I skipped a duplicate in-progress task after restart to avoid repeating actions.",
        )

    async def _is_task_stuck(self, task: Task) -> bool:
        """Check if a task is stuck (RUNNING but no progress for threshold)."""
        if task.current_step_index >= len(task.steps):
            return False
        
        step = task.steps[task.current_step_index]
        if step.status != TaskStepStatus.RUNNING:
            return False
        
        step_started = getattr(step, 'started_at', None)
        if step_started:
            if isinstance(step_started, str):
                try:
                    step_started = datetime.fromisoformat(step_started)
                except:
                    return False
            
            now = datetime.now(timezone.utc)
            if step_started.tzinfo is None:
                step_started = step_started.replace(tzinfo=timezone.utc)
            
            stuck_duration = (now - step_started).total_seconds()
            if stuck_duration > STUCK_TASK_THRESHOLD_SECONDS:
                logger.warning(f"Task {task.id} step {task.current_step_index} stuck for {stuck_duration}s")
                return True
        
        return False

    async def _recover_stuck_task(self, task: Task):
        """Attempt to recover a stuck task."""
        step = task.steps[task.current_step_index]
        
        if step.retry_count >= STEP_MAX_RETRIES:
            logger.error(f"⛔ Task {task.id} step {task.current_step_index} stuck and max retries exceeded")
            await self.manager.fail_task(task.id, f"Terminated: Step stuck and exceeded retries")
            RuntimeMetrics.increment("tasks_failed_total")
        else:
            logger.info(f"Retrying stuck task {task.id} step {task.current_step_index}")
            step.status = TaskStepStatus.PENDING
            step.retry_count += 1
            await self.manager.store.update_task(task)

    async def _execute_next_step(self, task: Task):
        """Dispatch next step to appropriate worker with timeout and exception handling."""
        step_start_ts = time.perf_counter()
        step = task.steps[task.current_step_index]
        idempotency_key = f"{task.id}:{task.current_step_index}:{step.retry_count}"

        transitioned, refreshed_task = await self.atomic_store.update_step_status(
            task.id,
            task.current_step_index,
            TaskStepStatus.RUNNING,
            idempotency_key=idempotency_key,
        )
        if not transitioned:
            logger.warning(
                f"Skipping task {task.id} step {task.current_step_index}: atomic RUNNING transition failed"
            )
            return
        if refreshed_task:
            task = refreshed_task
            step = task.steps[task.current_step_index]
        
        if step.status == TaskStepStatus.DONE:
            task.current_step_index += 1
            await self.manager.store.update_task(task)
            return

        if step.status == TaskStepStatus.FAILED:
            logger.error(f"⛔ Step {step.id} is FAILED. Failing task {task.id}")
            await self.manager.fail_task(task.id, f"Terminated: Step {task.current_step_index + 1} failed permanently.")
            return

        try:
            worker_type = step.worker if isinstance(step.worker, WorkerType) else WorkerType(str(step.worker).strip().lower())
        except Exception:
            worker_type = WorkerType.GENERAL
        worker = self.registry.get_worker(worker_type)
        
        worker_type_str = normalize_intent(worker.worker_type)
        
        permission_check = self._check_tool_permission(step, worker)
        if not permission_check["allowed"]:
            logger.warning(f"🔒 Tool '{step.tool}' not allowed for worker '{worker_type_str}'. Replanning...")
            await self.manager.store.add_log(task.id, f"Tool permission denied: {step.tool}. Attempting replan.")
            
            step.tool = None
            step.parameters = {}
            step.status = TaskStepStatus.PENDING
            await self.manager.store.update_task(task)
            
            await self.manager.store.add_log(task.id, f"Step modified: tool removed, falling back to reasoning-only mode")
            logger.info(f"🔄 Step {task.current_step_index} modified: tool removed for worker {worker_type_str}")
        
        worker_type_display = worker_type_str.upper() if worker_type_str else "UNKNOWN"
        logger.info(f"⚙️ Dispatching Task {task.id} Step {task.current_step_index} to {worker_type_display}")
        
        try:
            success = await asyncio.wait_for(
                worker.execute_step(task, step),
                timeout=STEP_TIMEOUT_SECONDS
            )
            
            if success:
                await self.atomic_store.update_step_status(
                    task.id,
                    task.current_step_index,
                    TaskStepStatus.DONE,
                    result=step.result,
                    idempotency_key=idempotency_key,
                )
                task.current_step_index += 1
                await self.manager.store.update_task(task)
                self._log_execution_event(
                    task=task,
                    tool_name=step.tool or "reasoning",
                    latency_ms=(time.perf_counter() - step_start_ts) * 1000.0,
                    outcome="success",
                )
                logger.info(f"✅ Step completed. Advancing to {task.current_step_index}")
            else:
                self._log_execution_event(
                    task=task,
                    tool_name=step.tool or "reasoning",
                    latency_ms=(time.perf_counter() - step_start_ts) * 1000.0,
                    outcome="failed",
                )
                if step.status == TaskStepStatus.FAILED and step.retry_count >= STEP_MAX_RETRIES:
                    await self.manager.fail_task(task.id, f"Terminated: Step failed after {STEP_MAX_RETRIES} retries")
                    RuntimeMetrics.increment("tasks_failed_total")
        
        except asyncio.TimeoutError:
            logger.error(f"⏱️ Step execution timed out for task {task.id} step {task.current_step_index}")
            step.status = TaskStepStatus.FAILED
            step.error = f"Step timed out after {STEP_TIMEOUT_SECONDS}s"
            await self.atomic_store.update_step_status(
                task.id,
                task.current_step_index,
                TaskStepStatus.FAILED,
                error=step.error,
                idempotency_key=idempotency_key,
            )
            await self.manager.store.update_task(task)
            self._log_execution_event(
                task=task,
                tool_name=step.tool or "reasoning",
                latency_ms=(time.perf_counter() - step_start_ts) * 1000.0,
                outcome="timeout",
            )
            RuntimeMetrics.increment("step_timeouts_total")
        
        except Exception as e:
            logger.error(f"❌ Step execution failed for task {task.id}: {e}", exc_info=True)
            step.status = TaskStepStatus.FAILED
            step.error = str(e)
            await self.atomic_store.update_step_status(
                task.id,
                task.current_step_index,
                TaskStepStatus.FAILED,
                error=step.error,
                idempotency_key=idempotency_key,
            )
            await self.manager.store.update_task(task)
            self._log_execution_event(
                task=task,
                tool_name=step.tool or "reasoning",
                latency_ms=(time.perf_counter() - step_start_ts) * 1000.0,
                outcome="error",
            )
            RuntimeMetrics.increment("step_failures_total")

    def _check_tool_permission(self, step, worker) -> dict:
        """Check if the tool is allowed for the worker type."""
        from core.tasks.workers.capabilities import get_allowed_tools
        
        if step.tool is None:
            return {"allowed": True, "reason": "No tool specified"}
        
        worker_type = worker.worker_type if hasattr(worker, "worker_type") else WorkerType.GENERAL
        allowed_tools = get_allowed_tools(worker_type)
        tool_name = step.tool.lower().strip()
        
        for allowed in allowed_tools:
            if allowed.lower() == tool_name:
                return {"allowed": True, "tool": allowed}
        
        return {
            "allowed": False, 
            "reason": f"Tool '{step.tool}' not in allowed list for {step.worker}",
            "allowed_tools": allowed_tools
        }

if __name__ == "__main__":
    import os
    logging.basicConfig(level=logging.INFO)
    user_id = os.getenv("USER_ID", "default_user")
    
    async def main():
        worker = TaskWorker(user_id)
        await worker.start()
        try:
            while True:
                await asyncio.sleep(3600)
        except (KeyboardInterrupt, SystemExit):
            await worker.stop()

    asyncio.run(main())
