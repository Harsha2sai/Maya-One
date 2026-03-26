from enum import Enum, auto
from dataclasses import dataclass, field
from typing import Optional
import time

class ProviderState(Enum):
    HEALTHY = auto()
    DEGRADED = auto()
    RECONNECTING = auto()
    OFFLINE = auto()

@dataclass
class ProviderHealth:
    name: str
    state: ProviderState = ProviderState.HEALTHY
    last_success_ts: float = field(default_factory=time.time)
    failure_count: int = 0
    last_error: Optional[str] = None

    def mark_success(self):
        self.state = ProviderState.HEALTHY
        self.last_success_ts = time.time()
        self.failure_count = 0
        self.last_error = None

    def mark_failure(self, error: str):
        self.failure_count += 1
        self.last_error = error
        if self.failure_count > 3:
            self.state = ProviderState.OFFLINE
        else:
            self.state = ProviderState.DEGRADED

    def __str__(self):
        return f"ProviderHealth(name={self.name}, state={self.state.name}, failures={self.failure_count}, last_error={self.last_error})"
