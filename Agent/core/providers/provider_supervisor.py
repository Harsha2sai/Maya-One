import asyncio
import logging
import time
from typing import Dict, Any, Optional, Callable
from .provider_health import ProviderHealth, ProviderState

logger = logging.getLogger(__name__)

_PROVIDER_HOST_MAP = {
    "groq": "api.groq.com",
    "elevenlabs": "api.elevenlabs.io",
    "deepgram": "api.deepgram.com",
    "cartesia": "api.cartesia.ai",
    "openai": "api.openai.com",
}


def _provider_host(name: str) -> str:
    normalized = str(name or "").strip().lower()
    return _PROVIDER_HOST_MAP.get(normalized, normalized or "unknown")

class CircuitBreaker:
    """
    Circuit breaker pattern to prevent cascading failures.
    
    States:
    - CLOSED: Normal operation, requests allowed
    - OPEN: Too many failures, requests blocked
    - HALF_OPEN: Testing recovery, limited requests allowed
    """
    
    def __init__(self, failure_threshold: int = 5, timeout: int = 60, success_threshold: int = 2):
        self.failure_count = 0
        self.success_count = 0
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.success_threshold = success_threshold
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
        self.last_failure_time = None
    
    def record_failure(self) -> None:
        """Record a failure and potentially open the circuit."""
        self.failure_count += 1
        self.success_count = 0
        self.last_failure_time = time.time()
        
        if self.failure_count >= self.failure_threshold:
            if self.state != "OPEN":
                self.state = "OPEN"
                logger.warning(f"🔴 Circuit breaker OPEN after {self.failure_count} failures")
    
    def record_success(self) -> None:
        """Record a success and potentially close the circuit."""
        if self.state == "HALF_OPEN":
            self.success_count += 1
            if self.success_count >= self.success_threshold:
                self.state = "CLOSED"
                self.failure_count = 0
                self.success_count = 0
                logger.info("🟢 Circuit breaker CLOSED after successful recovery")
        elif self.state == "CLOSED":
            # Gradually reduce failure count on success
            self.failure_count = max(0, self.failure_count - 1)
    
    def should_allow_request(self) -> bool:
        """Check if a request should be allowed based on circuit state."""
        if self.state == "CLOSED":
            return True
        elif self.state == "OPEN":
            # Check if timeout has elapsed to enter half-open state
            if self.last_failure_time and (time.time() - self.last_failure_time >= self.timeout):
                self.state = "HALF_OPEN"
                self.success_count = 0
                logger.info("🟡 Circuit breaker entering HALF_OPEN state")
                return True
            return False
        else:  # HALF_OPEN
            return True
    
    def get_state(self) -> str:
        """Get current circuit breaker state."""
        return self.state

class ProviderSupervisor:
    def __init__(self, failure_threshold: int = 5, recovery_timeout_s: float = 60.0, success_threshold: int = 2):
        self._providers: Dict[str, Any] = {}
        self._health_map: Dict[str, ProviderHealth] = {}
        self._circuit_breakers: Dict[str, CircuitBreaker] = {}
        self._reconnect_tasks: Dict[str, asyncio.Task] = {}
        self._running = False
        self._monitoring_task: Optional[asyncio.Task] = None
        self._listeners: list[Callable[[str, ProviderHealth], Any]] = []
        self.failure_threshold = failure_threshold
        self.recovery_timeout_s = recovery_timeout_s
        self.success_threshold = success_threshold
        logger.info(
            "provider_supervisor_configured threshold=%d recovery_s=%.1f success_threshold=%d",
            failure_threshold, recovery_timeout_s, success_threshold
        )

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
        provider_name = _provider_host(name)
        self._providers[provider_name] = proxy
        if provider_name not in self._health_map:
            self._health_map[provider_name] = ProviderHealth(name=provider_name)
        if provider_name not in self._circuit_breakers:
            self._circuit_breakers[provider_name] = CircuitBreaker(
                failure_threshold=self.failure_threshold,
                timeout=int(self.recovery_timeout_s),
                success_threshold=self.success_threshold
            )
            logger.info(f"Registered provider for supervisor: {provider_name}")
        else:
            logger.info(f"Updated provider proxy for supervisor: {provider_name}")

    def get_health(self, name: str) -> Optional[ProviderHealth]:
        return self._health_map.get(name)

    def mark_failed(self, name: str, error: Exception):
        provider_name = _provider_host(name)
        health = self._health_map.get(provider_name)
        circuit_breaker = self._circuit_breakers.get(provider_name)
        
        # MONITORING
        from telemetry.session_monitor import get_session_monitor
        monitor = get_session_monitor()
        monitor.record_provider_failure(provider_name)
        
        if health:
            health.mark_failure(str(error))
            logger.warning(f"Provider {provider_name} failed: {error}. Health: {health}")
            
            # Record failure in circuit breaker
            if circuit_breaker:
                prev_state = circuit_breaker.state
                circuit_breaker.record_failure()
                new_state = circuit_breaker.state
                
                if prev_state != new_state:
                     monitor.record_circuit_breaker_state(provider_name, new_state)
                
                logger.debug(f"Circuit breaker state for {provider_name}: {circuit_breaker.get_state()}")
            
            self._notify_listeners(provider_name)
            
            if health.state == ProviderState.OFFLINE and provider_name not in self._reconnect_tasks:
                try:
                    asyncio.get_running_loop()
                except RuntimeError:
                    logger.debug(
                        "Skipping reconnect task scheduling for %s because no event loop is running",
                        provider_name,
                    )
                else:
                    self._reconnect_tasks[provider_name] = asyncio.create_task(
                        self._reconnect_loop(provider_name)
                    )

    def mark_healthy(self, name: str):
        provider_name = _provider_host(name)
        health = self._health_map.get(provider_name)
        circuit_breaker = self._circuit_breakers.get(provider_name)
        
        if health:
            if health.state != ProviderState.HEALTHY:
                logger.info(f"Provider {provider_name} restored to HEALTHY")
            health.mark_success()
            
            # Record success in circuit breaker
            if circuit_breaker:
                prev_state = circuit_breaker.state
                circuit_breaker.record_success()
                new_state = circuit_breaker.state
                
                if prev_state != new_state:
                     from telemetry.session_monitor import get_session_monitor
                     monitor = get_session_monitor()
                     monitor.record_circuit_breaker_state(provider_name, new_state)

                logger.debug(f"Circuit breaker state for {provider_name}: {circuit_breaker.get_state()}")
            
            self._notify_listeners(provider_name)
            if provider_name in self._reconnect_tasks:
                self._reconnect_tasks[provider_name].cancel()
                del self._reconnect_tasks[provider_name]
    
    def should_allow_request(self, name: str) -> bool:
        """Check if requests to this provider should be allowed based on circuit breaker state."""
        circuit_breaker = self._circuit_breakers.get(_provider_host(name))
        if circuit_breaker:
            return circuit_breaker.should_allow_request()
        return True  # Allow if no circuit breaker configured
    
    def get_circuit_state(self, name: str) -> str:
        """Get the current circuit breaker state for a provider."""
        circuit_breaker = self._circuit_breakers.get(_provider_host(name))
        return circuit_breaker.get_state() if circuit_breaker else "UNKNOWN"

    def record_failure(self, name: str, error: Exception | None = None) -> None:
        self.mark_failed(name, error or RuntimeError("provider failure"))

    def record_success(self, name: str) -> None:
        self.mark_healthy(name)

    def is_open(self, name: str) -> bool:
        return self.get_circuit_state(name) == "OPEN"

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
                
                # Log system health periodically
                monitor.log_system_health()
                
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
