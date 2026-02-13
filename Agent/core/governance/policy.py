from typing import Dict
from .types import RiskLevel

class ToolRiskPolicy:
    """
    Maps tool names to their associated risk levels.
    """
    
    # Default policy definition
    _POLICY: Dict[str, RiskLevel] = {
        # READ_ONLY / LOW
        "get_current_datetime": RiskLevel.READ_ONLY,
        "get_date": RiskLevel.READ_ONLY,
        "get_time": RiskLevel.READ_ONLY,
        "get_weather": RiskLevel.LOW,
        "search_web": RiskLevel.LOW,

        # MEDIUM (Personal Data Read)
        "list_alarms": RiskLevel.MEDIUM,
        "list_reminders": RiskLevel.MEDIUM,
        "list_notes": RiskLevel.MEDIUM,
        "read_note": RiskLevel.MEDIUM,
        "list_calendar_events": RiskLevel.MEDIUM,
        
        # HIGH (Actions / Write)
        "set_alarm": RiskLevel.HIGH,
        "delete_alarm": RiskLevel.HIGH,
        "set_reminder": RiskLevel.HIGH,
        "delete_reminder": RiskLevel.HIGH,
        "create_note": RiskLevel.HIGH,
        "delete_note": RiskLevel.HIGH,
        "create_calendar_event": RiskLevel.HIGH,
        "delete_calendar_event": RiskLevel.HIGH,
        "send_email": RiskLevel.HIGH,
        "open_app": RiskLevel.HIGH,
        "close_app": RiskLevel.HIGH,
        
        # CRITICAL
        # (Reserved for future system tools like file deletion)
    }

    @classmethod
    def get_risk(cls, tool_name: str) -> RiskLevel:
        """
        Get the risk level for a specific tool.
        Defaults to HIGH if the tool is unknown, for safety.
        """
        # Normalize tool name to lower case
        normalized_name = tool_name.lower()
        return cls._POLICY.get(normalized_name, RiskLevel.HIGH)
