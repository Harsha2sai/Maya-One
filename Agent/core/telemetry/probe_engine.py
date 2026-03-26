
import asyncio
import logging
from core.tasks.task_manager import TaskManager
from providers import ProviderFactory
from config.settings import settings

logger = logging.getLogger(__name__)

class ProbeEngine:
    """
    Runs continuous background probes to verify system health.
    Tests: LLM connectivity, Database access, etc.
    """
    def __init__(self, interval: float = 300.0): # 5 minutes
        self.interval = interval
        self._running = False
        self._task = None
        
    async def start(self):
        if self._running: return
        self._running = True
        self._task = asyncio.create_task(self._probe_loop())
        logger.info("🩺 Probe Engine started")

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("🛑 Probe Engine stopped")

    async def _probe_loop(self):
        while self._running:
            try:
                await self.run_probes()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Probe Engine crashed: {e}")
            
            await asyncio.sleep(self.interval)

    async def run_probes(self):
        logger.info("🧪 Running System Probes...")
        results = {}
        
        # 1. DB Probe
        try:
             # Just instantiate task manager to check DB connection implicitly? 
             # Or call a lightweight method.
             mgr = TaskManager("system_probe")
             await mgr.get_active_tasks()
             results["db"] = "OK"
        except Exception as e:
             results["db"] = f"FAIL: {e}"

        # 2. LLM Probe
        try:
            # Simple ping
            # This consumes tokens, so keep it minimal.
            # verify we can get an LLM instance at least.
            llm = ProviderFactory.get_llm(settings.llm_provider, settings.llm_model)
            if llm:
                results["llm_init"] = "OK"
            else:
                results["llm_init"] = "FAIL: Valid Provider not returned"
        except Exception as e:
            results["llm_init"] = f"FAIL: {e}"

        # Log results
        failures = [k for k, v in results.items() if v != "OK"]
        if failures:
            logger.error(f"health_probe_failed: {results}")
        else:
            logger.info("✅ All System Probes Passed")
