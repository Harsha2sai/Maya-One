from core.agents.subagent_circuit_breaker import CircuitState, SubagentCircuitBreaker


def test_subagent_circuit_breaker_state_transitions():
    breaker = SubagentCircuitBreaker(failure_threshold=3, half_open_cooldown_s=0.01)
    agent_id = "subagent_coder"

    assert breaker.can_call(agent_id) is True
    assert breaker.get_state(agent_id) == CircuitState.CLOSED

    breaker.record_failure(agent_id)
    breaker.record_failure(agent_id)
    assert breaker.get_state(agent_id) == CircuitState.CLOSED

    breaker.record_failure(agent_id)
    assert breaker.get_state(agent_id) == CircuitState.OPEN
    assert breaker.can_call(agent_id) is False

