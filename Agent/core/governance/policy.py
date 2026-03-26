from typing import Dict
from pathlib import Path
from .types import RiskLevel
import os

# Safe path roots - all file tools validate against these
SAFE_PATH_ROOTS = [
    Path.home() / "Downloads",
    Path.home() / "Documents",
    Path.home() / "Desktop",
    Path.home() / ".maya",
]

# Network controls
ALLOWED_NETWORK_SCHEMES = ["https"]
BLOCKED_DOWNLOAD_EXTENSIONS = [
    ".sh", ".exe", ".bat", ".msi", ".ps1", ".cmd",
    ".vbs", ".jar", ".deb", ".rpm",
]

# Shell command blocklist
SHELL_BLOCKED_PATTERNS = [
    r"rm\s+-rf\s+/",
    r"dd\s+if=",
    r"mkfs",
    r">\s*/dev/",
    r"curl.+\|\s*(?:bash|sh)",
    r"wget.+\|\s*(?:bash|sh)",
    r"chmod\s+777\s+/",
]

def validate_safe_path(path: str) -> bool:
    """
    Validate that a path is within safe directories.
    Catches: ../../ traversal, symlink attacks, /etc/ access.
    Python 3.8 compatible - uses relative_to() not is_relative_to().
    """
    # Block path traversal attempts
    if ".." in str(path):
        return False
    try:
        resolved = Path(path).expanduser().resolve()
        for root in SAFE_PATH_ROOTS:
            try:
                resolved.relative_to(root.resolve())
                return True
            except ValueError:
                continue
        return False
    except Exception:
        return False

def validate_download_url(url: str) -> tuple[bool, str]:
    """
    Reject HTTP (not HTTPS) and blocked file extensions.
    Returns: (is_valid, reason_or_ok_message)
    """
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)

        if parsed.scheme not in ALLOWED_NETWORK_SCHEMES:
            return False, f"scheme '{parsed.scheme}' not allowed - use https"

        for ext in BLOCKED_DOWNLOAD_EXTENSIONS:
            if parsed.path.lower().endswith(ext):
                return False, f"file extension '{ext}' blocked for security"

        return True, "ok"
    except Exception as e:
        return False, f"URL parsing failed: {e}"


# Browser domain controls
BROWSER_ALLOWED_DOMAINS = "*"  # Default: allow all. Override in .env to restrict


class BrowserDomainBlocked(Exception):
    """Raised when navigation is blocked to a disallowed domain."""


async def _on_navigation(response, task_id: str = None):
    """
    Post-redirect domain check. Called after every browser navigation.
    Fires in browser context to validate the domain matches allowed list.
    """
    from urllib.parse import urlparse
    allowed_domains = os.getenv("BROWSER_ALLOWED_DOMAINS", BROWSER_ALLOWED_DOMAINS)
    if allowed_domains == "*":
        return  # All domains allowed
    domain = urlparse(response.url).netloc
    if not any(domain == d or domain.endswith(f".{d}") for d in allowed_domains.split(",")):
        raise BrowserDomainBlocked(f"Navigation blocked to {domain} — not in allowed list")

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
        "web_search": RiskLevel.LOW,
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
        "set_volume": RiskLevel.HIGH,
        "take_screenshot": RiskLevel.HIGH,

        # MEDIUM (File read)
        "list_directory": RiskLevel.MEDIUM,
        "search_files": RiskLevel.MEDIUM,
        "file_exists": RiskLevel.MEDIUM,
        "file_metadata": RiskLevel.MEDIUM,
        "file_hash": RiskLevel.MEDIUM,
        "count_file_lines": RiskLevel.MEDIUM,
        "read_file": RiskLevel.MEDIUM,
        "read_file_chunk": RiskLevel.MEDIUM,
        "fetch_webpage": RiskLevel.MEDIUM,

        # HIGH (File write operations)
        "move_file": RiskLevel.HIGH,
        "copy_file": RiskLevel.HIGH,
        "download_file": RiskLevel.HIGH,
        "create_pdf": RiskLevel.HIGH,
        "create_docx": RiskLevel.HIGH,

        # CRITICAL (Browser automation - high risk)
        "browser_open": RiskLevel.CRITICAL,
        "browser_current_url": RiskLevel.CRITICAL,
        "browser_get_elements": RiskLevel.CRITICAL,
        "browser_wait_for": RiskLevel.CRITICAL,
        "browser_fill": RiskLevel.CRITICAL,
        "browser_click": RiskLevel.CRITICAL,
        "browser_get_text": RiskLevel.CRITICAL,
        "browser_screenshot": RiskLevel.CRITICAL,
        "browser_close": RiskLevel.CRITICAL,
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
