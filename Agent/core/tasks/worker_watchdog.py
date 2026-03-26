
import asyncio
import logging
from datetime import datetime
import pytz

from core.tasks.task_manager import TaskManager
from core.tasks.task_models import TaskStatus, TaskPriority
from config.settings import settings

logger = logging.getLogger(__name__)

STUCK_THRESHOLD_SECONDS = 300 # 5 minutes

class WorkerWatchdog:
    """
    Supervisor for the Autonomous Agent System.
    Monitors active tasks for stuck states, resource exhaustion, and anomalies.
    """
    def __init__(self, user_id: str, interval: float = 30.0):
        self.user_id = user_id
        self.interval = interval
        self.manager = TaskManager(user_id)
        self._running = False
        self._task = None

    async def start(self):
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._watchdog_loop())
        logger.info(f"🐶 Worker Watchdog started for user {self.user_id}")

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("🛑 Worker Watchdog stopped")

    async def _watchdog_loop(self):
        while self._running:
            try:
                await self._scan_tasks()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Watchdog scan failed: {e}")
            
            await asyncio.sleep(self.interval)

    async def _scan_tasks(self):
        """Analyze system health and task states."""
        active_tasks = await self.manager.get_active_tasks()
        
        now = datetime.now(pytz.UTC)
        
        for task in active_tasks:
            # Check for Stuck Tasks (RUNNING but not updated recently)
            if task.status == TaskStatus.RUNNING:
                last_update = task.updated_at
                if last_update.tzinfo is None:
                    last_update = last_update.replace(tzinfo=pytz.UTC)
                
                stuck_duration = (now - last_update).total_seconds()
                
                if stuck_duration > STUCK_THRESHOLD_SECONDS:
                    logger.warning(f"⚠️ Task {task.id} appears stuck (no update for {stuck_duration}s).")
                    
                    # Log finding
                    await self.manager.store.add_log(task.id, f"Watchdog: Task appears stuck (no progress for {int(stuck_duration)}s).")
                    
                    # Auto-Fail if excessively stuck (> 10 mins?)
                    if stuck_duration > 600:
                         logger.error(f"⛔ Killing stuck task {task.id}")
                         await self.manager.fail_task(task.id, "Watchdog: Terminated due to inactivity timeout.")

            # Check for Infinite Retry Loops (Pending steps with high retry count?)
            # TaskWorker handles retry limits logic, but Watchdog can be a second pair of eyes.
            current_step = None
            if task.steps and task.current_step_index < len(task.steps):
                current_step = task.steps[task.current_step_index]
            
            if current_step and current_step.retry_count > 5: # Hard limit if worker logic fails
                 logger.warning(f"⚠️ Task {task.id} step {current_step.id} retried {current_step.retry_count} times. Killing.")
                 await self.manager.fail_task(task.id, "Watchdog: Terminated due to excessive step retries.")

        # Telemetry (Log snapshot)
        running_count = len([t for t in active_tasks if t.status == TaskStatus.RUNNING])
        pending_count = len([t for t in active_tasks if t.status == TaskStatus.PENDING])
        logger.info(f"📊 [Telemetry] Active: {len(active_tasks)} (Running: {running_count}, Pending: {pending_count})")
