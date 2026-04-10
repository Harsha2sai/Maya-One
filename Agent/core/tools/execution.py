"""
P31 Tier 1 — Shell execution tool.
Bash with timeout, sandbox check, and stderr capture.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

# Patterns that are always blocked regardless of permission mode
_BLOCKED_PATTERNS = [
    re.compile(r"curl\s+.*\|\s*(ba)?sh", re.IGNORECASE),
    re.compile(r"wget\s+.*\|\s*(ba)?sh", re.IGNORECASE),
    re.compile(r"rm\s+-rf\s+/(?!\S)", re.IGNORECASE),   # rm -rf / (root only)
    re.compile(r"git\s+push\s+--force\b", re.IGNORECASE),
    re.compile(r":\(\)\{.*\}", re.IGNORECASE),            # fork bomb
    re.compile(r"mkfs\.", re.IGNORECASE),                 # filesystem format
]

DEFAULT_TIMEOUT_S = 120


def _is_blocked(command: str) -> Optional[str]:
    """Return a reason string if the command matches a blocked pattern, else None."""
    for pat in _BLOCKED_PATTERNS:
        if pat.search(command):
            return f"blocked_pattern: {pat.pattern}"
    return None


async def bash(
    command: str,
    description: Optional[str] = None,
    timeout: int = DEFAULT_TIMEOUT_S,
    dangerously_disable_sandbox: bool = False,
) -> str:
    """Execute a shell command and return combined stdout + stderr.

    Args:
        command: Shell command to run.
        description: Human-readable description of what the command does.
        timeout: Timeout in seconds (default: 120).
        dangerously_disable_sandbox: Skip the blocked-pattern check.
            Only set True when you are certain the command is safe.

    Returns:
        Combined stdout/stderr output, or an error/block message.
    """
    if not dangerously_disable_sandbox:
        reason = _is_blocked(command)
        if reason:
            logger.warning("bash_blocked command=%r reason=%s", command[:120], reason)
            return f"Error: command blocked ({reason})"

    logger.info("bash_exec command=%r timeout=%ds", command[:120], timeout)

    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout_b, stderr_b = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.communicate()
            return f"Error: command timed out after {timeout}s"

        stdout = stdout_b.decode(errors="replace").rstrip()
        stderr = stderr_b.decode(errors="replace").rstrip()
        exit_code = proc.returncode

        parts: list[str] = []
        if stdout:
            parts.append(stdout)
        if stderr:
            parts.append(f"[stderr]\n{stderr}")
        if exit_code != 0:
            parts.append(f"[exit code: {exit_code}]")

        output = "\n".join(parts) if parts else "(no output)"
        logger.info("bash_done exit_code=%d output_len=%d", exit_code, len(output))
        return output

    except Exception as e:
        logger.error("bash_error command=%r: %s", command[:120], e)
        return f"Error: {e}"
