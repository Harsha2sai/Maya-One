from __future__ import annotations

from typing import Annotated, Any, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

SCHEMA_VERSION = "1.0"


class _EventBase(BaseModel):
    """Base envelope for all data-channel events."""

    model_config = ConfigDict(extra="forbid")

    type: str
    schema_version: Literal["1.0"]
    timestamp: int
    trace_id: Optional[str] = None


class UserMessageEvent(_EventBase):
    type: Literal["user_message"]
    turn_id: str
    content: str


class AssistantDeltaEvent(_EventBase):
    type: Literal["assistant_delta"]
    turn_id: str
    content: str
    seq: int


class AssistantFinalEvent(_EventBase):
    type: Literal["assistant_final"]
    turn_id: str
    content: str
    voice_text: str
    sources: list[dict[str, Any]] = Field(default_factory=list)
    tool_invocations: list[dict[str, Any]] = Field(default_factory=list)
    mode: str = "normal"
    memory_updated: bool = False
    confidence: float = 0.0
    structured_data: dict[str, Any] = Field(default_factory=dict)


class AgentThinkingEvent(_EventBase):
    type: Literal["agent_thinking"]
    turn_id: str
    state: str


class ToolExecutionEvent(_EventBase):
    type: Literal["tool_execution"]
    turn_id: str
    tool_name: str
    status: str
    # Backward compatibility with existing Flutter handler.
    tool: Optional[str] = None
    message: Optional[str] = None
    task_id: Optional[str] = None
    conversation_id: Optional[str] = None


class AgentSpeakingEvent(_EventBase):
    type: Literal["agent_speaking"]
    turn_id: str
    status: str


class TurnCompleteEvent(_EventBase):
    type: Literal["turn_complete"]
    turn_id: str
    status: str


class ErrorEvent(_EventBase):
    type: Literal["error"]
    turn_id: Optional[str] = None
    message: str
    code: Optional[str] = None


class SourceItemSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    url: str
    domain: str
    snippet: str
    provider: str


class ResearchResultEvent(_EventBase):
    type: Literal["research_result"]
    turn_id: str
    query: str
    summary: str
    sources: list[SourceItemSchema] = Field(default_factory=list)
    task_id: Optional[str] = None
    conversation_id: Optional[str] = None


class MediaResultEvent(_EventBase):
    type: Literal["media_result"]
    turn_id: str
    action: str
    provider: str
    track_name: Optional[str] = None
    artist: Optional[str] = None
    album_art_url: Optional[str] = None
    track_url: Optional[str] = None
    task_id: Optional[str] = None
    conversation_id: Optional[str] = None


class SystemResultEvent(_EventBase):
    type: Literal["system_result"]
    turn_id: Optional[str] = None
    action_type: str
    success: bool = False
    message: str = ""
    detail: str = ""
    rollback_available: bool = False
    task_id: Optional[str] = None
    conversation_id: Optional[str] = None


class ConfirmationRequiredEvent(_EventBase):
    type: Literal["confirmation_required"]
    action_type: str
    description: str = ""
    destructive: bool = False
    timeout_seconds: int = 30


class ConfirmationResponseEvent(_EventBase):
    type: Literal["confirmation_response"]
    confirmed: bool = False


AgentEventPayload = Annotated[
    Union[
        UserMessageEvent,
        AssistantDeltaEvent,
        AssistantFinalEvent,
        AgentThinkingEvent,
        ToolExecutionEvent,
        AgentSpeakingEvent,
        TurnCompleteEvent,
        ErrorEvent,
        ResearchResultEvent,
        MediaResultEvent,
        SystemResultEvent,
        ConfirmationRequiredEvent,
        ConfirmationResponseEvent,
    ],
    Field(discriminator="type"),
]

_EVENT_ADAPTER = TypeAdapter(AgentEventPayload)


def validate_chat_event_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize a chat_events payload."""
    event = _EVENT_ADAPTER.validate_python(payload)
    return event.model_dump(exclude_none=True)


def chat_event_json_schema() -> dict[str, Any]:
    """Return JSON Schema for the discriminated event payload union."""
    return _EVENT_ADAPTER.json_schema()
