from .types import UserRole, RiskLevel
from .policy import ToolRiskPolicy
from core.permissions.contracts import PermissionChecker, PermissionMode

class ExecutionGate:
    """
    Decides whether a tool execution request should be allowed or denied.
    Wraps PermissionChecker — mode policy is activated via set_mode().
    """
    _permission_checker = PermissionChecker()
    _mode_policy_active = False   # Activated when set_mode() is called

    @classmethod
    def set_mode(cls, mode: PermissionMode) -> None:
        """Switch the active permission mode and activate mode policy."""
        cls._permission_checker.set_mode(PermissionMode(mode))
        cls._mode_policy_active = True

    @classmethod
    def get_mode(cls) -> PermissionMode:
        """Return the currently active permission mode."""
        return cls._permission_checker.config.default_mode

    @classmethod
    def reset_mode(cls) -> None:
        """Reset to DEFAULT mode and deactivate mode policy (for testing)."""
        cls._permission_checker.set_mode(PermissionMode.DEFAULT)
        cls._mode_policy_active = False

    @staticmethod
    def check_access(tool_name: str, user_role: UserRole) -> bool:
        """
        Check if the user has sufficient permissions to execute the tool.
        """
        result = ExecutionGate._permission_checker.check(
            tool_name,
            user_role,
            {
                "mode": ExecutionGate._permission_checker.config.default_mode,
                "respect_mode_policy": ExecutionGate._mode_policy_active,
            },
        )
        return bool(result.allowed)

    @staticmethod
    def get_denial_reason(tool_name: str, user_role: UserRole) -> str:
        """
        Get a human-readable reason for denial.
        """
        tool_risk = ToolRiskPolicy.get_risk(tool_name)
        return (
            f"Permission Denied: '{tool_name}' is classified as {tool_risk.name} risk. "
            f"Your role ({user_role.name}) only allows up to {user_role.max_risk.name} risk."
        )
