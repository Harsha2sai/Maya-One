"""
Shared turn context object for the Maya-One orchestration pipeline.

TurnContext is constructed once per incoming message at the top of
handle_message and passed through to handler dispatch callsites.
It replaces the pattern of passing message/user_id/tool_context/origin
as separate positional arguments at every callsite.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field, replace
from typing import Any


@dataclass
class TurnContext:
    """Immutable context for a single user turn."""

    message: str
    user_id: str
    tool_context: Any
    origin: str = "chat"

    # Filled after routing decision
    route: str = ""

    # Optional identifiers - populated from tool_context where available
    turn_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str = ""
    trace_id: str = ""

    def with_route(self, route: str) -> "TurnContext":
        """Return a copy with route filled in."""
        return replace(self, route=route)

    @classmethod
    def from_handle_message_args(
        cls,
        message: str,
        user_id: str,
        tool_context: Any,
        origin: str = "chat",
    ) -> "TurnContext":
        """Construct from the standard handle_message argument set."""
        session_id = getattr(tool_context, "session_id", None) or ""
        trace_id = getattr(tool_context, "trace_id", None) or ""
        return cls(
            message=message,
            user_id=user_id,
            tool_context=tool_context,
            origin=origin,
            session_id=session_id,
            trace_id=trace_id,
        )
