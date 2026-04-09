"""Circuit breaker for subagent health isolation."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class _CircuitRecord:
    state: CircuitState = CircuitState.CLOSED
    consecutive_failures: int = 0
    opened_at: float = 0.0
    half_open_probe_in_flight: bool = False


@dataclass
class SubagentCircuitBreaker:
    failure_threshold: int = 3
    half_open_cooldown_s: float = 60.0
    _records: Dict[str, _CircuitRecord] = field(default_factory=dict)

    def _record_for(self, agent_id: str) -> _CircuitRecord:
        key = str(agent_id or "").strip() or "unknown_agent"
        record = self._records.get(key)
        if record is None:
            record = _CircuitRecord()
            self._records[key] = record
        return record

    def can_call(self, agent_id: str) -> bool:
        now = time.monotonic()
        record = self._record_for(agent_id)
        if record.state == CircuitState.CLOSED:
            return True
        if record.state == CircuitState.OPEN:
            if (now - record.opened_at) >= max(1.0, self.half_open_cooldown_s):
                record.state = CircuitState.HALF_OPEN
                record.half_open_probe_in_flight = False
            else:
                return False
        if record.state == CircuitState.HALF_OPEN:
            if record.half_open_probe_in_flight:
                return False
            record.half_open_probe_in_flight = True
            return True
        return False

    def record_success(self, agent_id: str) -> None:
        record = self._record_for(agent_id)
        record.state = CircuitState.CLOSED
        record.consecutive_failures = 0
        record.opened_at = 0.0
        record.half_open_probe_in_flight = False

    def record_failure(self, agent_id: str) -> CircuitState:
        now = time.monotonic()
        record = self._record_for(agent_id)
        if record.state == CircuitState.HALF_OPEN:
            record.state = CircuitState.OPEN
            record.opened_at = now
            record.half_open_probe_in_flight = False
            record.consecutive_failures = max(1, record.consecutive_failures)
            return record.state

        record.consecutive_failures += 1
        if record.consecutive_failures >= max(1, self.failure_threshold):
            record.state = CircuitState.OPEN
            record.opened_at = now
            record.half_open_probe_in_flight = False
        return record.state

    def get_state(self, agent_id: str) -> CircuitState:
        return self._record_for(agent_id).state

