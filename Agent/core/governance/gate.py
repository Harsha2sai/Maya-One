from .types import UserRole, RiskLevel
from .policy import ToolRiskPolicy

class ExecutionGate:
    """
    Decides whether a tool execution request should be allowed or denied.
    """

    @staticmethod
    def check_access(tool_name: str, user_role: UserRole) -> bool:
        """
        Check if the user has sufficient permissions to execute the tool.
        """
        # 1. Get Risk Level of the tool
        tool_risk = ToolRiskPolicy.get_risk(tool_name)
        
        # 2. Get Max Allowed Risk for the user
        user_max_risk = user_role.max_risk
        
        # 3. Compare
        # If the tool's risk is greater than what the user is allowed, deny.
        if tool_risk > user_max_risk:
            return False
            
        return True

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
