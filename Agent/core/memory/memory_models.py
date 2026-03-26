
from enum import Enum
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime, timezone
import uuid

class MemorySource(str, Enum):
    CONVERSATION = "conversation"
    TASK_RESULT = "task_result"
    FILE = "file"
    TOOL_OUTPUT = "tool_output"
    KNOWLEDGE = "knowledge"

class MemoryItem(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    text: str
    source: MemorySource
    metadata: Dict[str, Any] = Field(default_factory=dict)
    embedding: Optional[List[float]] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    model_config = ConfigDict(use_enum_values=True)
