from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional


class SubAgentStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"


class SubAgentType(str, Enum):
    CODER = "coder"
    REVIEWER = "reviewer"
    RESEARCHER = "researcher"
    ARCHITECT = "architect"
    TESTER = "tester"


@dataclass
class SubAgentInstance:
    id: str
    agent_type: str
    task: str
    status: SubAgentStatus
    result: Optional[str] = None
    error: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    worktree_path: Optional[Path] = None
    background: bool = False


class SubAgentCapacityError(Exception):
    pass


class SubAgentTimeoutError(Exception):
    pass


class WorktreeError(Exception):
    pass
