from .types import UserRole, RiskLevel
from .policy import ToolRiskPolicy
from core.permissions.contracts import PermissionChecker, PermissionMode

class ExecutionGate:
    """
    Decides whether a tool execution request should be allowed or denied.
    """
    _permission_checker = PermissionChecker()

    @staticmethod
    def check_access(tool_name: str, user_role: UserRole) -> bool:
        """
        Check if the user has sufficient permissions to execute the tool.
        """
        result = ExecutionGate._permission_checker.check(
            tool_name,
            user_role,
            {
                # Keep legacy runtime behavior unless explicit mode policy is requested.
                "mode": PermissionMode.DEFAULT,
                "respect_mode_policy": False,
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
