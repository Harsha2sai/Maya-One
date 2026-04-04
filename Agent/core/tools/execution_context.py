"""
ExecutionContext - Production-ready context for tool execution.

Replaces the inline MockJobContext/SimpleContext that were used in production
tool execution paths. This dataclass provides a clean, typed interface for
context data passed to tools.

Created: 2026-04-04 (P16-01)
"""
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class JobContext:
    """Minimal job context for tools that need user_id."""
    user_id: str


@dataclass
class ExecutionContext:
    """
    Production execution context for tool calls.

    Provides all context fields needed by tools in a typed, immutable container.
    Replaces the inline MockJobContext/SimpleContext classes that were previously
    defined inside execute_tool().

    Attributes:
        user_id: User identifier for the tool call
        session_id: Session identifier (often same as turn_id in voice mode)
        task_id: Task identifier if part of a task flow
        trace_id: Distributed tracing ID
        user_role: User role for permission checks
        room: LiveKit room reference (if in voice mode)
        turn_id: Conversation turn ID
        conversation_id: Conversation ID for persistence
        job_context: Wrapped JobContext for tools expecting this interface
    """
    user_id: str = "unknown"
    session_id: Optional[str] = None
    task_id: Optional[str] = None
    trace_id: Optional[str] = None
    user_role: Any = None  # UserRole type, but avoid circular import
    room: Any = None
    turn_id: Optional[str] = None
    conversation_id: Optional[str] = None

    # Backward compatibility: provide job_context interface
    job_context: JobContext = field(default=None)

    def __post_init__(self):
        """Initialize job_context for backward compatibility."""
        if self.job_context is None:
            self.job_context = JobContext(user_id=self.user_id)


def create_execution_context(
    context: Any,
    default_user_id: str = "unknown",
    default_session_id: Optional[str] = None,
) -> ExecutionContext:
    """
    Create ExecutionContext from a context object (typically a JobContext or similar).

    This factory function extracts all known context attributes safely,
    using defaults for missing values.

    Args:
        context: Source context object (may be None)
        default_user_id: Default user ID if not found in context
        default_session_id: Default session ID if not found in context

    Returns:
        ExecutionContext with all fields populated
    """
    if context is None:
        return ExecutionContext(
            user_id=default_user_id,
            session_id=default_session_id,
        )

    # Import here to avoid circular dependency
    try:
        from core.governance.types import UserRole
        default_role = UserRole.GUEST
    except ImportError:
        default_role = None

    return ExecutionContext(
        user_id=getattr(context, 'user_id', default_user_id) or default_user_id,
        session_id=getattr(context, 'session_id', None) or getattr(context, 'turn_id', default_session_id),
        task_id=getattr(context, 'task_id', None),
        trace_id=getattr(context, 'trace_id', None),
        user_role=getattr(context, 'user_role', default_role),
        room=getattr(context, 'room', None),
        turn_id=getattr(context, 'turn_id', None),
        conversation_id=getattr(context, 'conversation_id', None),
    )