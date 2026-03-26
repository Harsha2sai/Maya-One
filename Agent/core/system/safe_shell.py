from __future__ import annotations

import logging
import shlex
import subprocess

logger = logging.getLogger(__name__)

BLOCKED_COMMANDS = {
    "sudo",
    "su",
    "mkfs",
    "dd",
    "mount",
    "umount",
    "iptables",
    "chmod",
    "chown",
    "passwd",
    "visudo",
    "systemctl",
    "service",
    "init",
    "shutdown",
    "reboot",
    "fdisk",
    "parted",
    "wipefs",
}


def safe_shell(command: str, timeout: int = 10) -> tuple[bool, str]:
    raw_command = str(command or "").strip()
    if not raw_command:
        return False, "Command is empty"

    try:
        base = shlex.split(raw_command)[0].split("/")[-1]
    except Exception as exc:
        return False, f"Command parse failed: {exc}"

    if base in BLOCKED_COMMANDS or any(base == f"{blocked}.ext4" or base.startswith(f"{blocked}.") for blocked in BLOCKED_COMMANDS):
        logger.warning("safe_shell_blocked command=%s", base)
        return False, f"Command '{base}' is not permitted"

    for blocked in BLOCKED_COMMANDS:
        if f"| {blocked}" in raw_command or f"; {blocked}" in raw_command or f"&& {blocked}" in raw_command:
            logger.warning("safe_shell_blocked chained_command=%s", blocked)
            return False, f"Piped command '{blocked}' is not permitted"

    try:
        result = subprocess.run(
            raw_command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        output = (result.stdout or result.stderr or "").strip()
        return result.returncode == 0, output
    except subprocess.TimeoutExpired:
        return False, "Command timed out"
    except Exception as exc:
        return False, str(exc)
