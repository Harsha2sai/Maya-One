"""Tool execution and implicit preference capture helpers."""
from __future__ import annotations

import logging
import time
from typing import Any, Callable, Dict

from core.action.adapters import from_system_action, to_tool_receipt
from core.action.verifier import ActionVerifier
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
        self._verifier = ActionVerifier()

    @staticmethod
    def _action_receipts_enabled() -> bool:
        return bool(getattr(settings, "action_receipts_enabled", False))

    @staticmethod
    def _action_verification_enabled() -> bool:
        return bool(getattr(settings, "action_verification_enabled", False))

    def _build_action_intent(
        self,
        *,
        tool_name: str,
        args: Dict[str, Any],
        tool_context: Any,
    ) -> Any:
        turn_state = getattr(self._owner, "turn_state", None) or {}
        session_id = (
            getattr(tool_context, "session_id", None)
            or getattr(self._owner, "_current_session_id", None)
            or getattr(getattr(self._owner, "room", None), "name", None)
            or "console_session"
        )
        turn_id = (
            getattr(tool_context, "turn_id", None)
            or str(turn_state.get("current_turn_id") or "")
            or "unknown_turn"
        )
        trace_id = (
            getattr(tool_context, "trace_id", None)
            or str(turn_state.get("trace_id") or "")
            or "unknown_trace"
        )
        source_route = str(turn_state.get("last_route") or "tool_executor")
        return from_system_action(
            {
                "tool_name": tool_name,
                "target": args.get("app_name") or args.get("folder_name") or args.get("command") or "",
                "query": args.get("query") or "",
                "confidence": 1.0,
                "entity": "tool",
            },
            session_id=session_id,
            turn_id=turn_id,
            trace_id=trace_id,
            source_route=source_route,
        )

    async def _attach_receipt_if_enabled(
        self,
        *,
        intent: Any,
        tool_name: str,
        args: Dict[str, Any],
        raw_result: Any,
        normalized_result: Dict[str, Any],
        latency_ms: int,
        session_id: str,
    ) -> Dict[str, Any]:
        result = dict(normalized_result or {})
        if not self._action_receipts_enabled():
            return result

        verification = None
        if self._action_verification_enabled() and intent is not None:
            try:
                verification = await self._verifier.verify(
                    intent_id=intent.intent_id,
                    tool_name=tool_name,
                    args=args,
                    normalized_result=result,
                    raw_result=raw_result,
                )
            except Exception as verify_err:
                logger.warning("action_verification_failed tool=%s error=%s", tool_name, verify_err)

        receipt = to_tool_receipt(
            intent_id=getattr(intent, "intent_id", ""),
            tool_name=tool_name,
            raw_result=raw_result,
            normalized_result=result,
            duration_ms=latency_ms,
            verification=verification,
        )
        result["_tool_receipt"] = receipt.to_dict()

        recorder = getattr(self._owner, "_record_action_receipt", None)
        if callable(recorder):
            try:
                await recorder(session_id=session_id, receipt=receipt)
            except Exception as record_err:
                logger.warning("action_receipt_record_failed tool=%s error=%s", tool_name, record_err)

        return result

    async def execute_tool_call(
        self,
        tool_name: str,
        args: Dict[str, Any],
        user_id: str,
        tool_context: Any = None,
    ) -> tuple[Any, ToolInvocation]:
        router = get_router()
        logger.info(f"🔧 CHAT path executing tool: {tool_name}({args})")
        intent = self._build_action_intent(tool_name=tool_name, args=args, tool_context=tool_context)
        session_id = (
            getattr(tool_context, "session_id", None)
            or getattr(self._owner, "_current_session_id", None)
            or getattr(getattr(self._owner, "room", None), "name", None)
            or "console_session"
        )
        record_intent = getattr(self._owner, "_record_action_intent", None)
        if callable(record_intent):
            try:
                await record_intent(session_id=session_id, intent=intent)
            except Exception as intent_err:
                logger.warning("action_intent_record_failed tool=%s error=%s", tool_name, intent_err)
        if not router.tool_executor:
            normalized_failure = self._owner._normalize_tool_result(
                tool_name=tool_name,
                raw_result=None,
                error_code="tool_not_wired",
            )
            normalized_failure = await self._attach_receipt_if_enabled(
                intent=intent,
                tool_name=tool_name,
                args=args,
                raw_result=None,
                normalized_result=normalized_failure,
                latency_ms=0,
                session_id=session_id,
            )
            return (
                normalized_failure,
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
            normalized = self._owner._normalize_tool_result(
                tool_name=tool_name,
                raw_result=raw_result,
            )
            result = await self._attach_receipt_if_enabled(
                intent=intent,
                tool_name=tool_name,
                args=args,
                raw_result=raw_result,
                normalized_result=normalized,
                latency_ms=latency_ms,
                session_id=session_id,
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
            normalized_failure = self._owner._normalize_tool_result(
                tool_name=tool_name,
                raw_result=None,
                error_code="tool_exception",
            )
            normalized_failure = await self._attach_receipt_if_enabled(
                intent=intent,
                tool_name=tool_name,
                args=args,
                raw_result=None,
                normalized_result=normalized_failure,
                latency_ms=latency_ms,
                session_id=session_id,
            )
            return (
                normalized_failure,
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
