from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from enum import Enum
from datetime import datetime

class TaskStepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"

class WorkerType(str, Enum):
    GENERAL = "general"
    RESEARCH = "research"
    AUTOMATION = "automation"
    SYSTEM = "system"

class VerificationType(str, Enum):
    """Structured verification types for task step execution."""
    FILE_EXISTS = "file_exists"
    COMMAND_EXIT_CODE = "command_exit_code"
    DOM_CHECK = "dom_check"
    OUTPUT_CONTAINS = "output_contains"
    URL_MATCHES = "url_matches"

class TaskStep(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    description: str
    tool: Optional[str] = None
    parameters: Optional[Dict[str, Any]] = None
    
    status: TaskStepStatus = TaskStepStatus.PENDING
    result: Optional[str] = None
    error: Optional[str] = None
    retry_count: int = 0
    
    worker: WorkerType = WorkerType.GENERAL
    
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)
    completed_at: Optional[datetime] = None

    # Verification fields
    verification_type: Optional[VerificationType] = None
    expected_path: Optional[str] = None  # for FILE_EXISTS
    expected_selector: Optional[str] = None  # for DOM_CHECK
    expected_url_pattern: Optional[str] = None  # for URL_MATCHES
    success_criteria: Optional[str] = None  # for OUTPUT_CONTAINS
    step_timeout_seconds: int = 30

    model_config = {
        "use_enum_values": True
    }

import uuid
