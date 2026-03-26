
from enum import Enum
from typing import List, Dict, Optional, Any
from pydantic import BaseModel, Field
from datetime import datetime, timezone
import uuid
from core.tasks.task_steps import TaskStep

class TaskStatus(str, Enum):
    PENDING = "PENDING"
    PLANNING = "PLANNING"
    PLAN_FAILED = "PLAN_FAILED"
    RUNNING = "RUNNING"
    WAITING = "WAITING"
    STALE = "STALE"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"

class TaskPriority(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"

class TaskLog(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    task_id: str
    message: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class Task(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    title: str
    description: Optional[str] = None
    status: TaskStatus = TaskStatus.PENDING
    priority: TaskPriority = TaskPriority.MEDIUM

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    steps: List[TaskStep] = Field(default_factory=list)
    current_step_index: int = 0
    progress_notes: Optional[List[str]] = Field(default_factory=list)
    
    # Anti-Loop / Delegation Tracking
    delegation_depth: int = 0
    delegation_chain: Optional[List[str]] = Field(default_factory=list) # List of worker types in chain
    
    result: Optional[str] = None
    error: Optional[str] = None

    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)
