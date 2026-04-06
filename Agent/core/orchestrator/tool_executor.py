"""Tool execution and implicit preference capture helpers."""
from __future__ import annotations

import logging
import time
from typing import Any, Callable, Dict

from config.settings import settings
from core.governance.types import UserRole
from core.response.agent_response import ToolInvocation
from core.routing.router import get_router

logger = logging.getLogger(__name__)


class ToolExecutor:
    """Owns router-backed tool execution and direct-tool preference capture."""

    def __init__(self, *, owner: Any, coerce_user_role_fn: Callable[..., UserRole]):
        self._owner = owner
        self._coerce_user_role = coerce_user_role_fn

    async def execute_tool_call(
        self,
        tool_name: str,
        args: Dict[str, Any],
        user_id: str,
        tool_context: Any = None,
    ) -> tuple[Any, ToolInvocation]:
        router = get_router()
        logger.info(f"🔧 CHAT path executing tool: {tool_name}({args})")
        if not router.tool_executor:
            return (
                self._owner._normalize_tool_result(
                    tool_name=tool_name,
                    raw_result=None,
                    error_code="tool_not_wired",
                ),
                ToolInvocation(tool_name=tool_name, status="failed", latency_ms=None),
            )

        if tool_context is None:
            default_role = self._coerce_user_role(
                getattr(settings, "default_client_role", "USER"),
                default_role=UserRole.USER,
            )
            tool_context = type(
                "ToolExecutionContext",
                (),
                {
                    "user_id": user_id,
                    "user_role": default_role,
                    "room": self._owner.room,
                    "turn_id": None,
                },
            )()

        start = time.time()
        try:
            raw_result = await router.tool_executor(
                tool_name,
                args,
                context=tool_context,
            )
            latency_ms = int((time.time() - start) * 1000)
            result = self._owner._normalize_tool_result(
                tool_name=tool_name,
                raw_result=raw_result,
            )
            status = "success" if result.get("success", True) else "failed"
            logger.info(
                "tool_invoked tool_name=%s status=%s latency_ms=%s",
                tool_name,
                status,
                latency_ms,
            )
            return result, ToolInvocation(tool_name=tool_name, status=status, latency_ms=latency_ms)
        except Exception as e:
            latency_ms = int((time.time() - start) * 1000)
            logger.warning(
                "tool_call_failed_safe_wrap tool_name=%s error=%s",
                tool_name,
                e,
            )
            return (
                self._owner._normalize_tool_result(
                    tool_name=tool_name,
                    raw_result=None,
                    error_code="tool_exception",
                ),
                ToolInvocation(tool_name=tool_name, status="failed", latency_ms=latency_ms),
            )

    def capture_implicit_preference_from_direct_tool(
        self,
        tool_name: str,
        tool_args: Dict[str, Any],
        user_id: str,
    ) -> None:
        app_name = ""
        if tool_name == "open_app":
            app_name = str(tool_args.get("app_name") or "").strip().lower()
            for browser in ("firefox", "chrome", "brave", "edge"):
                if browser in app_name:
                    self._owner._queue_preference_update(
                        user_id,
                        "preferred_browser",
                        browser,
                        source="direct_open_app",
                    )
                    break
            for music_app in ("spotify", "youtube", "vlc"):
                if music_app in app_name:
                    self._owner._queue_preference_update(
                        user_id,
                        "music_app",
                        music_app,
                        source="direct_open_app",
                    )
                    break
        elif tool_name == "set_volume":
            try:
                percent = int(tool_args.get("percent"))
            except Exception:
                return
            if 0 <= percent <= 100:
                self._owner._queue_preference_update(
                    user_id,
                    "preferred_volume",
                    percent,
                    source="direct_set_volume",
                )
