"""Formal handoff contracts for internal specialist delegation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


ExecutionMode = Literal["inline", "background", "planning"]
HandoffStatus = Literal["completed", "rejected", "needs_tool", "needs_followup", "failed"]
NextAction = Literal["respond", "continue", "background", "fallback_to_maya"]
SignalName = Literal[
    "transfer_to_research",
    "transfer_to_system_operator",
    "transfer_to_planner",
    "transfer_to_media",
    "transfer_to_scheduling",
    "transfer_to_security",
    "transfer_to_documentation",
    "transfer_to_monitoring",
    "transfer_to_subagent_coder",
    "transfer_to_subagent_reviewer",
    "transfer_to_subagent_architect",
]


@dataclass
class AgentHandoffRequest:
    handoff_id: str
    trace_id: str
    conversation_id: str | None
    task_id: str | None
    parent_agent: str
    active_agent: str
    target_agent: str
    intent: str
    user_text: str
    context_slice: str
    execution_mode: ExecutionMode
    delegation_depth: int
    max_depth: int
    handoff_reason: str
    parent_handoff_id: str | None = None
    delegation_chain_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentHandoffResult:
    handoff_id: str
    trace_id: str
    source_agent: str
    status: HandoffStatus
    user_visible_text: str | None
    voice_text: str | None
    structured_payload: dict[str, Any]
    next_action: NextAction
    error_code: str | None = None
    error_detail: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentCapabilityMatch:
    agent_name: str
    confidence: float
    reason: str
    hard_constraints_passed: bool


@dataclass
class HandoffSignal:
    signal_name: SignalName
    reason: str
    execution_mode: ExecutionMode
    context_hint: str | None = None
