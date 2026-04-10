"""
Permission System Contracts for Phase 4

Defines the six permission modes and hook system from
Claude Code Integration Extended Plan.
"""

from enum import Enum
from typing import Optional, Callable, List, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime


class PermissionMode(str, Enum):
    """Six permission modes from Claude Code."""
    DEFAULT = "default"           # Ask for all destructive actions
    ACCEPT_EDITS = "acceptEdits"  # Auto-accept file edits, ask for shell
    PLAN = "plan"                 # Plan mode - ask before executing
    AUTO = "auto"                 # Auto-accept low-risk, ask for high-risk
    DONT_ASK = "dontAsk"          # Assume yes to all prompts (dangerous)
    BYPASS = "bypassPermissions"  # No permission checks at all


class PermissionHookType(str, Enum):
    """Hook points in the permission lifecycle."""
    PRE_TOOL_USE = "pre_tool_use"
    POST_TOOL_USE = "post_tool_use"
    PRE_EDIT = "pre_edit"
    PRE_WRITE = "pre_write"
    PRE_BASH = "pre_bash"
    ON_MODE_CHANGE = "on_mode_change"


class PermissionRequest(BaseModel):
    """Request for permission to execute a tool/action."""
    tool_name: str
    params: Dict[str, Any]
    mode: PermissionMode
    file_path: Optional[str] = None
    is_destructive: bool = False
    requires_confirmation: bool = True
    risk_level: str = Field(default="medium", pattern="^(low|medium|high|critical)$")
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class PermissionResult(BaseModel):
    """Result of a permission check."""
    allowed: bool
    mode: PermissionMode
    reason: Optional[str] = None
    hook_results: List[Dict[str, Any]] = Field(default_factory=list)
    bypass_reason: Optional[str] = None  # If bypassPermissions was used


class PermissionHook(BaseModel):
    """A hook that can intercept permission decisions."""
    name: str
    hook_type: PermissionHookType
    handler: Optional[Callable] = None  # Set at runtime
    priority: int = 0  # Higher = runs first
    enabled: bool = True


class ProtectedPath(BaseModel):
    """Path protection configuration."""
    path_pattern: str
    allowed_modes: List[PermissionMode]
    require_additional_approval: bool = True
    description: Optional[str] = None


class PermissionConfig(BaseModel):
    """Configuration for the permission system."""
    default_mode: PermissionMode = PermissionMode.DEFAULT
    protected_paths: List[ProtectedPath] = Field(default_factory=list)
    hooks: List[PermissionHook] = Field(default_factory=list)
    auto_approve_patterns: List[str] = Field(default_factory=list)
    safety_classifier_enabled: bool = True


class ModeTransition(BaseModel):
    """Record of a mode change."""
    from_mode: PermissionMode
    to_mode: PermissionMode
    timestamp: datetime
    reason: Optional[str] = None
    user_initiated: bool = True
