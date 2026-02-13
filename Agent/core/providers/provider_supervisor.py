import asyncio
import logging
import time
from typing import Dict, Any, Optional, Callable
from .provider_health import ProviderHealth, ProviderState

logger = logging.getLogger(__name__)

class ProviderSupervisor:
    def __init__(self):
        self._providers: Dict[str, Any] = {}
        self._health_map: Dict[str, ProviderHealth] = {}
        self._reconnect_tasks: Dict[str, asyncio.Task] = {}
        self._running = False
        self._monitoring_task: Optional[asyncio.Task] = None
        self._listeners: list[Callable[[str, ProviderHealth], Any]] = []

    def add_listener(self, callback: Callable[[str, ProviderHealth], Any]):
        """Add a listener for provider health changes."""
        self._listeners.append(callback)

    def _notify_listeners(self, name: str):
        health = self._health_map.get(name)
        if health:
            for listener in self._listeners:
                try:
                    # Run synchronously to avoid race conditions, or schedule?
                    # Since this might be called from async context, better to maybe schedule if logic is heavy?
                    # For now, let's assume listeners are fast or async-compatible.
                    # If callback is async, we should await it?
                    # To be safe, we'll check if it's a coroutine.
                    if asyncio.iscoroutinefunction(listener):
                        asyncio.create_task(listener(name, health))
                    else:
                        listener(name, health)
                except Exception as e:
                    logger.error(f"Error notifying listener for {name}: {e}")

    def register_provider(self, name: str, proxy: Any):
        self._providers[name] = proxy
        self._health_map[name] = ProviderHealth(name=name)
        logger.info(f"Registered provider for supervisor: {name}")

    def get_health(self, name: str) -> Optional[ProviderHealth]:
        return self._health_map.get(name)

    def mark_failed(self, name: str, error: Exception):
        health = self._health_map.get(name)
        if health:
            health.mark_failure(str(error))
            logger.warning(f"Provider {name} failed: {error}. Health: {health}")
            self._notify_listeners(name)
            
            if health.state == ProviderState.OFFLINE and name not in self._reconnect_tasks:
                self._reconnect_tasks[name] = asyncio.create_task(self._reconnect_loop(name))

    def mark_healthy(self, name: str):
        health = self._health_map.get(name)
        if health:
            if health.state != ProviderState.HEALTHY:
                logger.info(f"Provider {name} restored to HEALTHY")
            health.mark_success()
            self._notify_listeners(name)
            if name in self._reconnect_tasks:
                self._reconnect_tasks[name].cancel()
                del self._reconnect_tasks[name]

    async def start(self):
        if self._running:
            return
        self._running = True
        self._monitoring_task = asyncio.create_task(self._main_monitoring_loop())
        logger.info("Provider Supervisor started")

    async def stop(self):
        self._running = False
        if self._monitoring_task:
            self._monitoring_task.cancel()
        for task in self._reconnect_tasks.values():
            task.cancel()
        logger.info("Provider Supervisor stopped")

    async def _main_monitoring_loop(self):
        """Background monitoring loop to check if any provider needs attention"""
        from telemetry.session_monitor import get_session_monitor
        monitor = get_session_monitor()
        
        while self._running:
            try:
                for name, health in self._health_map.items():
                    # Report downtime if not healthy
                    if health.state != ProviderState.HEALTHY:
                        downtime = time.time() - health.last_success_ts
                        metric_name = f"{name}_downtime"
                        monitor.record_metric(metric_name, downtime)

                    if health.state == ProviderState.OFFLINE and name not in self._reconnect_tasks:
                        logger.info(f"Triggering background reconnect for {name}")
                        self._reconnect_tasks[name] = asyncio.create_task(self._reconnect_loop(name))
                await asyncio.sleep(5)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in supervisor monitoring loop: {e}")
                await asyncio.sleep(5)

    async def _reconnect_loop(self, name: str):
        """Exponential backoff reconnect loop for a specific provider"""
        backoff_schedule = [2, 5, 10, 30]
        attempt = 0
        
        from telemetry.session_monitor import get_session_monitor
        monitor = get_session_monitor()
        
        while self._running:
            try:
                sleep_time = backoff_schedule[min(attempt, len(backoff_schedule) - 1)]
                logger.info(f"Attempting reconnect for {name} in {sleep_time}s (attempt {attempt + 1})")
                await asyncio.sleep(sleep_time)
                
                # Record reconnect attempt
                monitor.record_metric("reconnect_attempts", 1, increment=True)
                
                proxy = self._providers.get(name)
                if proxy and hasattr(proxy, 'attempt_reconnect'):
                    success = await proxy.attempt_reconnect()
                    if success:
                        logger.info(f"Reconnect successful for {name}")
                        self.mark_healthy(name)
                        break
                
                attempt += 1
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error during reconnect attempt for {name}: {e}")
                attempt += 1
