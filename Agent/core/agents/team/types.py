from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from core.agents.subagent.types import SubAgentInstance, SubAgentStatus


# ── P30: New team mode types ──────────────────────────────────────────────────

class TeamMode(str, Enum):
    PARALLEL = "parallel"
    SEQUENTIAL = "sequential"
    REVIEW = "review"


@dataclass
class TeamResult:
    mode: TeamMode
    instances: List[SubAgentInstance] = field(default_factory=list)
    iterations: List[dict] = field(default_factory=list)
    final_output: Optional[str] = None
    approved: bool = False

    @property
    def succeeded(self) -> bool:
        return all(i.status == SubAgentStatus.COMPLETED for i in self.instances)

    def summary(self) -> str:
        if self.mode == TeamMode.REVIEW:
            return (
                f"Review loop: {len(self.iterations)} iteration(s), "
                f"approved={self.approved}"
            )
        return (
            f"{self.mode.value}: {len(self.instances)} agent(s), "
            f"succeeded={self.succeeded}"
        )


# ── Legacy task-dispatch types (pre-P30, kept for backward compatibility) ─────

class TeamTaskStatus(str, Enum):
    PENDING   = "pending"
    RUNNING   = "running"
    COMPLETED = "completed"
    FAILED    = "failed"
    TIMEOUT   = "timeout"
    CANCELLED = "cancelled"


@dataclass
class TeamTask:
    task_id: str
    agent_name: str
    payload: Dict[str, Any] = field(default_factory=dict)
    timeout_s: Optional[float] = None


@dataclass
class TeamExecution:
    task_id: str
    agent_name: str
    status: TeamTaskStatus = TeamTaskStatus.PENDING
    result: Any = None
    error: Optional[str] = None
    duration_ms: float = 0.0
