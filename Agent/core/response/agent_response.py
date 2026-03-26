from typing import List, Optional, Dict, Any

try:
    from pydantic import BaseModel, Field, ConfigDict
    _PydanticV2 = True
except Exception:  # pragma: no cover - fallback for older pydantic
    from pydantic import BaseModel, Field
    ConfigDict = None
    _PydanticV2 = False


class Source(BaseModel):
    title: str
    url: str
    snippet: Optional[str] = None

    if _PydanticV2:
        model_config = ConfigDict(extra="ignore")
    else:
        class Config:
            extra = "ignore"


class ToolInvocation(BaseModel):
    tool_name: str
    status: str  # success | failed | skipped
    latency_ms: Optional[int] = None

    if _PydanticV2:
        model_config = ConfigDict(extra="ignore")
    else:
        class Config:
            extra = "ignore"


class AgentResponse(BaseModel):
    display_text: str
    voice_text: str
    sources: Optional[List[Source]] = None
    tool_invocations: Optional[List[ToolInvocation]] = None
    mode: str = Field(default="normal")
    memory_updated: bool = False
    confidence: float = 0.5
    structured_data: Optional[Dict[str, Any]] = None

    if _PydanticV2:
        model_config = ConfigDict(extra="ignore")
    else:
        class Config:
            extra = "ignore"
