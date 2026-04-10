"""
Scheduling Tools Contracts for Phase 4

CronCreate, CronDelete, CronList tools for background task scheduling.
"""

from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum


class CronTrigger(BaseModel):
    """Cron-style scheduling trigger."""
    minute: str = Field(default="0", description="Minute (0-59, */5, etc.)")
    hour: str = Field(default="*", description="Hour (0-23, */2, etc.)")
    day_of_month: str = Field(default="*", description="Day of month (1-31)")
    month: str = Field(default="*", description="Month (1-12)")
    day_of_week: str = Field(default="*", description="Day of week (0-6)")

    def to_cron_expression(self) -> str:
        """Convert to standard cron format."""
        return f"{self.minute} {self.hour} {self.day_of_month} {self.month} {self.day_of_week}"


class ScheduledTaskStatus(str, Enum):
    """Status of a scheduled task."""
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    ERROR = "error"


class ScheduledTask(BaseModel):
    """A task scheduled via cron."""
    id: str = Field(description="Unique schedule ID")
    task_type: str = Field(description="Type of task to execute")
    trigger: CronTrigger
    params: Dict[str, Any] = Field(default_factory=dict)
    status: ScheduledTaskStatus = ScheduledTaskStatus.ACTIVE
    created_at: datetime = Field(default_factory=datetime.utcnow)
    next_run: Optional[datetime] = None
    last_run: Optional[datetime] = None
    run_count: int = 0
    error_count: int = 0
    user_id: Optional[str] = None
    description: Optional[str] = None


class CronCreateRequest(BaseModel):
    """Request to create a scheduled task."""
    task_type: str = Field(description="Task type to schedule")
    cron_expression: Optional[str] = None
    trigger: Optional[CronTrigger] = None
    params: Dict[str, Any] = Field(default_factory=dict)
    description: Optional[str] = None
    user_id: Optional[str] = None


class CronCreateResult(BaseModel):
    """Result of creating a scheduled task."""
    success: bool
    schedule_id: Optional[str] = None
    next_run: Optional[datetime] = None
    error: Optional[str] = None


class CronDeleteRequest(BaseModel):
    """Request to delete a scheduled task."""
    schedule_id: str


class CronDeleteResult(BaseModel):
    """Result of deleting a scheduled task."""
    success: bool
    deleted_task: Optional[ScheduledTask] = None
    error: Optional[str] = None


class CronListRequest(BaseModel):
    """Request to list scheduled tasks."""
    user_id: Optional[str] = None
    status: Optional[ScheduledTaskStatus] = None
    task_type: Optional[str] = None


class CronListResult(BaseModel):
    """Result of listing scheduled tasks."""
    tasks: List[ScheduledTask] = Field(default_factory=list)
    total_count: int = 0
    active_count: int = 0
    paused_count: int = 0
