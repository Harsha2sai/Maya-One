import pytest
import asyncio
import time
from core.providers.provider_supervisor import CircuitBreaker, ProviderSupervisor
from core.providers.provider_health import ProviderState


class TestCircuitBreaker:
    """Test circuit breaker pattern implementation."""
    
    def test_circuit_breaker_initial_state(self):
        """Circuit breaker should start in CLOSED state."""
        cb = CircuitBreaker(failure_threshold=3, timeout=5)
        assert cb.get_state() == "CLOSED"
        assert cb.should_allow_request()
    
    def test_circuit_breaker_opens_after_threshold(self):
        """Circuit should open after reaching failure threshold."""
        cb = CircuitBreaker(failure_threshold=3, timeout=5)
        
        # Record failures
        cb.record_failure()
        assert cb.get_state() == "CLOSED"
        
        cb.record_failure()
        assert cb.get_state() == "CLOSED"
        
        cb.record_failure()
        assert cb.get_state() == "OPEN"
        assert not cb.should_allow_request()
    
    @pytest.mark.asyncio
    async def test_circuit_breaker_half_open_transition(self):
        """Circuit should transition to HALF_OPEN after timeout."""
        cb = CircuitBreaker(failure_threshold=2, timeout=1)
        
        # Open circuit
        cb.record_failure()
        cb.record_failure()
        assert cb.get_state() == "OPEN"
        assert not cb.should_allow_request()
        
        # Wait for timeout
        await asyncio.sleep(1.1)
        
        # Should allow request and enter HALF_OPEN
        assert cb.should_allow_request()
        assert cb.get_state() == "HALF_OPEN"
    
    @pytest.mark.asyncio
    async def test_circuit_breaker_recovery(self):
        """Circuit should close after successful recovery in HALF_OPEN state."""
        cb = CircuitBreaker(failure_threshold=2, timeout=1, success_threshold=2)
        
        # Open circuit
        cb.record_failure()
        cb.record_failure()
        assert cb.get_state() == "OPEN"
        
        # Wait for timeout and enter HALF_OPEN
        await asyncio.sleep(1.1)
        assert cb.should_allow_request()
        assert cb.get_state() == "HALF_OPEN"
        
        # Successful recovery
        cb.record_success()
        assert cb.get_state() == "HALF_OPEN"
        
        cb.record_success()
        assert cb.get_state() == "CLOSED"
        assert cb.failure_count == 0
    
    def test_circuit_breaker_gradual_recovery_in_closed(self):
        """Successful requests in CLOSED state should reduce failure count."""
        cb = CircuitBreaker(failure_threshold=5)
        
        # Record some failures
        cb.record_failure()
        cb.record_failure()
        assert cb.failure_count == 2
        
        # Success should reduce count
        cb.record_success()
        assert cb.failure_count == 1
        
        cb.record_success()
        assert cb.failure_count == 0


class TestProviderSupervisorCircuitBreaker:
    """Test circuit breaker integration with ProviderSupervisor."""
    
    @pytest.mark.asyncio
    async def test_supervisor_creates_circuit_breaker_on_register(self):
        """Supervisor should create circuit breaker for each provider."""
        supervisor = ProviderSupervisor()
        
        class MockProvider:
            pass
        
        supervisor.register_provider("test_llm", MockProvider())
        
        assert "test_llm" in supervisor._circuit_breakers
        assert supervisor.get_circuit_state("test_llm") == "CLOSED"
    
    @pytest.mark.asyncio
    async def test_supervisor_records_failures_in_circuit_breaker(self):
        """Supervisor should record failures in circuit breaker."""
        supervisor = ProviderSupervisor()
        
        class MockProvider:
            pass
        
        supervisor.register_provider("test_llm", MockProvider())
        
        # Record failures
        for _ in range(5):
            supervisor.mark_failed("test_llm", Exception("Test error"))
        
        # Circuit should be open
        assert supervisor.get_circuit_state("test_llm") == "OPEN"
        assert not supervisor.should_allow_request("test_llm")
    
    @pytest.mark.asyncio
    async def test_supervisor_records_successes_in_circuit_breaker(self):
        """Supervisor should record successes in circuit breaker."""
        supervisor = ProviderSupervisor()
        
        class MockProvider:
            pass
        
        # Register provider
        supervisor.register_provider("test_llm", MockProvider())
        
        # Replace with short-timeout circuit breaker for testing
        supervisor._circuit_breakers["test_llm"] = CircuitBreaker(
            failure_threshold=5,
            timeout=1,  # Short timeout for testing
            success_threshold=2
        )
        
        # Open circuit
        for _ in range(5):
            supervisor.mark_failed("test_llm", Exception("Test error"))
        
        assert supervisor.get_circuit_state("test_llm") == "OPEN"
        
        # Wait for timeout
        await asyncio.sleep(1.1)
        
        # Should allow request now (HALF_OPEN)
        assert supervisor.should_allow_request("test_llm")
        
        # Mark healthy to record success
        supervisor.mark_healthy("test_llm")
        supervisor.mark_healthy("test_llm")
        
        # Circuit should close after success threshold
        assert supervisor.get_circuit_state("test_llm") == "CLOSED"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
