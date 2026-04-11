"""Hooks package for event-driven automation."""

from .actions import ActionResult, HookAction, LogAction, NotifyAction, SkillAction
from .registry import HookBinding, HookRegistry
from .triggers import (
    AGENT_HANDOFF,
    MESSAGE_RECEIVED,
    SKILL_EXECUTED,
    TASK_COMPLETE,
    TASK_FAILED,
    HookTrigger,
)

__all__ = [
    "HookTrigger",
    "HookAction",
    "ActionResult",
    "NotifyAction",
    "SkillAction",
    "LogAction",
    "HookBinding",
    "HookRegistry",
    "TASK_COMPLETE",
    "TASK_FAILED",
    "AGENT_HANDOFF",
    "SKILL_EXECUTED",
    "MESSAGE_RECEIVED",
]
