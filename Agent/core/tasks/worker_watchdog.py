
import asyncio
import logging
import sqlite3
from datetime import datetime, timezone
import pytz

from core.tasks.task_manager import TaskManager
from core.tasks.task_models import TaskStatus, TaskPriority
from config.settings import settings

logger = logging.getLogger(__name__)

STUCK_THRESHOLD_SECONDS = 300 # 5 minutes
STUCK_TASK_THRESHOLD_SECONDS = 600  # 10 minutes before watchdog reclaims

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

    async def run_once(self):
        """Run a single watchdog scan (for external loop integration)."""
        await self._scan_tasks()

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

        # Reclaim pass: identify and fail tasks stuck beyond threshold
        await self._reclaim_stuck_tasks()

        # Telemetry (Log snapshot)
        running_count = len([t for t in active_tasks if t.status == TaskStatus.RUNNING])
        pending_count = len([t for t in active_tasks if t.status == TaskStatus.PENDING])
        logger.info(f"📊 [Telemetry] Active: {len(active_tasks)} (Running: {running_count}, Pending: {pending_count})")

    async def _reclaim_stuck_tasks(self):
        """Query for tasks stuck beyond STUCK_TASK_THRESHOLD_SECONDS and transition them to FAILED."""
        try:
            db_path = self.manager.store.backend.db_path
            now = datetime.now(timezone.utc).isoformat()
            threshold_seconds = STUCK_TASK_THRESHOLD_SECONDS
            
            # Calculate cutoff time
            import datetime as dt_module
            cutoff_time = (dt_module.datetime.now(timezone.utc) - dt_module.timedelta(seconds=threshold_seconds)).isoformat()
            
            with sqlite3.connect(db_path) as conn:
                conn.row_factory = sqlite3.Row
                
                # Find stuck RUNNING tasks
                cursor = conn.execute(
                    """
                    SELECT id, updated_at FROM tasks
                    WHERE status = 'RUNNING' AND updated_at < ?
                    """,
                    (cutoff_time,)
                )
                stuck_tasks = cursor.fetchall()
                
                for row in stuck_tasks:
                    task_id = row['id']
                    updated_at = row['updated_at']
                    age_seconds = (datetime.fromisoformat(now.replace('Z', '+00:00')) - datetime.fromisoformat(updated_at.replace('Z', '+00:00'))).total_seconds() if 'T' in str(updated_at) else 0
                    
                    # Update task to FAILED
                    conn.execute(
                        """
                        UPDATE tasks
                        SET status = ?, error = ?, updated_at = ?
                        WHERE id = ?
                        """,
                        ('FAILED', 'stuck_task_reclaimed_by_watchdog', now, task_id)
                    )
                    
                    # Update all running steps to failed
                    conn.execute(
                        """
                        UPDATE task_steps
                        SET status = ?, error = ?
                        WHERE task_id = ? AND status = 'running'
                        """,
                        ('failed', 'stuck_task_reclaimed_by_watchdog', task_id)
                    )
                    
                    logger.warning(f"🐕 stuck_task_reclaimed task_id={task_id} age_seconds={int(age_seconds)}")
                
                conn.commit()
        except Exception as e:
            logger.error(f"❌ Error in _reclaim_stuck_tasks: {e}")
