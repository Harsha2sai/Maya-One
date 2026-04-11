"""
Permission System Contracts for Phase 4.

Defines permission modes, hook system, and runtime permission checker.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from fnmatch import fnmatch
from typing import Any, Callable, Dict, List, Optional

from pydantic import BaseModel, Field


class PermissionMode(str, Enum):
    """Six permission modes from Claude Code."""

    DEFAULT = "default"  # Ask for all destructive actions
    ACCEPT_EDITS = "acceptEdits"  # Auto-accept file edits, ask for shell
    PLAN = "plan"  # Plan mode - ask before executing
    AUTO = "auto"  # Auto-accept low-risk, ask for high-risk
    DONT_ASK = "dontAsk"  # Assume yes to all prompts (dangerous)
    BYPASS = "bypassPermissions"  # No permission checks at all
    LOCKED = "locked"  # Emergency: nothing runs


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

    model_config = {"arbitrary_types_allowed": True}


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


class PermissionChecker:
    """Runtime permission evaluator for tool execution."""

    FILE_EDIT_HINTS = {
        "file_write",
        "create_note",
        "delete_note",
        "move_file",
        "copy_file",
        "create_pdf",
        "create_docx",
    }
    SHELL_HINTS = {"run_shell_command", "bash", "shell", "terminal"}

    def __init__(self, config: Optional[PermissionConfig] = None) -> None:
        self.config = config or PermissionConfig()
        self._hooks: List[PermissionHook] = list(self.config.hooks)

    def register_hook(self, hook: PermissionHook) -> None:
        self._hooks.append(hook)

    def set_mode(self, mode: PermissionMode) -> None:
        self.config.default_mode = PermissionMode(mode)

    def check(
        self,
        tool_name: str,
        user_role: Any,
        context: Optional[Dict[str, Any]] = None,
    ) -> PermissionResult:
        context = dict(context or {})
        mode = self._resolve_mode(context.get("mode") or context.get("permission_mode"))

        role_result = self._check_role_risk(tool_name, user_role)
        if not role_result.allowed:
            role_result.mode = mode
            return role_result

        request = self._build_request(tool_name=tool_name, mode=mode, context=context)
        hook_results, hook_block = self._run_pre_tool_hooks(request, context)
        if hook_block is not None:
            hook_block.mode = mode
            hook_block.hook_results = hook_results
            return hook_block

        path_result = self._check_protected_paths(request)
        if path_result is not None:
            path_result.mode = mode
            path_result.hook_results = hook_results
            return path_result

        # ExecutionGate compatibility: when explicit mode policy isn't requested,
        # preserve legacy role-risk behavior (already validated above).
        if not bool(context.get("respect_mode_policy", False)):
            return PermissionResult(allowed=True, mode=mode, hook_results=hook_results)

        mode_result = self._check_mode_policy(request)
        mode_result.hook_results = hook_results
        return mode_result

    def _resolve_mode(self, mode_value: Any) -> PermissionMode:
        if mode_value is None:
            return self.config.default_mode
        if isinstance(mode_value, PermissionMode):
            return mode_value
        try:
            return PermissionMode(str(mode_value))
        except Exception:
            return self.config.default_mode

    def _build_request(self, *, tool_name: str, mode: PermissionMode, context: Dict[str, Any]) -> PermissionRequest:
        risk_level = self._tool_risk_label(tool_name)
        is_destructive = bool(context.get("is_destructive", False)) or risk_level in {"high", "critical"}
        return PermissionRequest(
            tool_name=str(tool_name or "").strip(),
            params=dict(context.get("params") or {}),
            mode=mode,
            file_path=str(context.get("file_path") or "").strip() or None,
            is_destructive=is_destructive,
            requires_confirmation=bool(context.get("requires_confirmation", True)),
            risk_level=risk_level,
        )

    def _run_pre_tool_hooks(
        self,
        request: PermissionRequest,
        context: Dict[str, Any],
    ) -> tuple[List[Dict[str, Any]], Optional[PermissionResult]]:
        results: List[Dict[str, Any]] = []
        hooks = sorted(
            [hook for hook in self._hooks if hook.enabled and hook.hook_type == PermissionHookType.PRE_TOOL_USE],
            key=lambda item: int(item.priority),
            reverse=True,
        )
        for hook in hooks:
            handler = hook.handler
            if not callable(handler):
                continue
            try:
                outcome = handler(request, context)
            except Exception as exc:
                results.append({"hook": hook.name, "status": "error", "error": str(exc)})
                continue

            if isinstance(outcome, dict):
                if "params" in outcome and isinstance(outcome["params"], dict):
                    request.params.update(outcome["params"])
                if "allow" in outcome and bool(outcome["allow"]) is False:
                    results.append({"hook": hook.name, "status": "blocked"})
                    return (
                        results,
                        PermissionResult(
                            allowed=False,
                            mode=request.mode,
                            reason=str(outcome.get("reason") or f"blocked by hook: {hook.name}"),
                        ),
                    )
                results.append({"hook": hook.name, "status": "modified"})
                continue

            if outcome is False:
                results.append({"hook": hook.name, "status": "blocked"})
                return (
                    results,
                    PermissionResult(
                        allowed=False,
                        mode=request.mode,
                        reason=f"blocked by hook: {hook.name}",
                    ),
                )

            results.append({"hook": hook.name, "status": "ok"})

        return results, None

    def _check_protected_paths(self, request: PermissionRequest) -> Optional[PermissionResult]:
        if not request.file_path:
            return None
        for protected in self.config.protected_paths:
            if not fnmatch(request.file_path, protected.path_pattern):
                continue
            if request.mode not in protected.allowed_modes:
                return PermissionResult(
                    allowed=False,
                    mode=request.mode,
                    reason=f"protected path denied: {protected.path_pattern}",
                )
            if protected.require_additional_approval and request.mode not in {
                PermissionMode.BYPASS,
                PermissionMode.DONT_ASK,
            }:
                return PermissionResult(
                    allowed=False,
                    mode=request.mode,
                    reason=f"additional approval required for protected path: {protected.path_pattern}",
                )
        return None

    def _check_mode_policy(self, request: PermissionRequest) -> PermissionResult:
        mode = request.mode
        tool = str(request.tool_name or "").strip().lower()

        if mode == PermissionMode.LOCKED:
            return PermissionResult(
                allowed=False,
                mode=mode,
                reason="locked mode: all tool execution suspended",
            )

        if mode == PermissionMode.BYPASS:
            return PermissionResult(
                allowed=True,
                mode=mode,
                bypass_reason="bypassPermissions mode enabled",
            )

        if mode == PermissionMode.DONT_ASK:
            return PermissionResult(allowed=True, mode=mode, reason="dontAsk mode auto-approval")

        if mode == PermissionMode.PLAN:
            return PermissionResult(
                allowed=False,
                mode=mode,
                reason="plan mode requires explicit approval before execution",
            )

        if mode == PermissionMode.ACCEPT_EDITS:
            if any(hint in tool for hint in self.SHELL_HINTS):
                return PermissionResult(
                    allowed=False,
                    mode=mode,
                    reason="acceptEdits mode still requires approval for shell commands",
                )
            if request.file_path or tool in self.FILE_EDIT_HINTS:
                return PermissionResult(allowed=True, mode=mode, reason="acceptEdits auto-approved edit")
            return PermissionResult(allowed=True, mode=mode, reason="acceptEdits allowed")

        if mode == PermissionMode.AUTO:
            if request.risk_level in {"low", "medium"}:
                return PermissionResult(allowed=True, mode=mode, reason="auto mode approved low/medium risk")
            return PermissionResult(
                allowed=False,
                mode=mode,
                reason="auto mode requires approval for high-risk action",
            )

        # DEFAULT mode
        if request.is_destructive or request.risk_level in {"high", "critical"}:
            return PermissionResult(
                allowed=False,
                mode=mode,
                reason="default mode requires confirmation for destructive actions",
            )
        return PermissionResult(allowed=True, mode=mode, reason="default mode allowed")

    def _check_role_risk(self, tool_name: str, user_role: Any) -> PermissionResult:
        # Import lazily to avoid circular dependencies with governance gate.
        from core.governance.policy import ToolRiskPolicy
        from core.governance.types import UserRole

        role = self._coerce_user_role(user_role)
        tool_risk = ToolRiskPolicy.get_risk(str(tool_name or "").strip().lower())
        if tool_risk > role.max_risk:
            return PermissionResult(
                allowed=False,
                mode=self.config.default_mode,
                reason=(
                    f"Permission Denied: '{tool_name}' is classified as {tool_risk.name} risk. "
                    f"Your role ({role.name}) only allows up to {role.max_risk.name} risk."
                ),
            )
        return PermissionResult(allowed=True, mode=self.config.default_mode)

    @staticmethod
    def _coerce_user_role(user_role: Any):
        from core.governance.types import UserRole

        if isinstance(user_role, UserRole):
            return user_role
        if isinstance(user_role, int):
            try:
                return UserRole(user_role)
            except Exception:
                return UserRole.GUEST
        text = str(getattr(user_role, "name", user_role) or "").strip().upper()
        if text in UserRole.__members__:
            return UserRole[text]
        return UserRole.GUEST

    @staticmethod
    def _tool_risk_label(tool_name: str) -> str:
        from core.governance.policy import ToolRiskPolicy

        risk = ToolRiskPolicy.get_risk(str(tool_name or "").strip().lower())
        name = str(getattr(risk, "name", "MEDIUM")).strip().upper()
        mapping = {
            "READ_ONLY": "low",
            "LOW": "low",
            "MEDIUM": "medium",
            "HIGH": "high",
            "CRITICAL": "critical",
        }
        return mapping.get(name, "medium")
