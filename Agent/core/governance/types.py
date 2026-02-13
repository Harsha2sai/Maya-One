from enum import IntEnum

class UserRole(IntEnum):
    """
    Defines the authority level of the user interacting with the agent.
    """
    GUEST = 0      # Low trust, limited access
    USER = 1       # Standard user, access to personal data
    TRUSTED = 2    # Trusted user, access to sensitive actions (e.g. email)
    ADMIN = 3      # Full system access

    @property
    def max_risk(self) -> 'RiskLevel':
        """
        Maps a user role to the maximum risk level they are allowed to execute.
        """
        # This mapping can be adjusted later in policy.py if needed, 
        # but defining a default here is safer.
        if self == UserRole.ADMIN:
            return RiskLevel.CRITICAL
        elif self == UserRole.TRUSTED:
            return RiskLevel.HIGH
        elif self == UserRole.USER:
            return RiskLevel.MEDIUM
        else:
            return RiskLevel.LOW

class RiskLevel(IntEnum):
    """
    Defines the potential risk associated with a tool execution.
    """
    READ_ONLY = 0  # Safe, no side effects (e.g. get_time)
    LOW = 1        # Minor side effects or public data retrieval (e.g. weather)
    MEDIUM = 2     # Access to personal data (e.g. list_notes)
    HIGH = 3       # Significant side effects (e.g. send_email, open_app)
    CRITICAL = 4   # System-level changes (e.g. delete_file, shutdown)
