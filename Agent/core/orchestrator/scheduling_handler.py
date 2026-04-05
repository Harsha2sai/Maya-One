"""
SchedulingHandler - Handles scheduling route execution.
Extracted from ChatResponseMixin (Phase 24).
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

from core.observability.trace_context import current_trace_id
from core.response.response_formatter import ResponseFormatter

logger = logging.getLogger(__name__)


class SchedulingHandler:
    """Owns scheduling intent execution and response formatting."""

    def __init__(self, *, owner: Any):
        self._owner = owner

    async def handle_scheduling_route(
        self,
        *,
        message: str,
        user_id: str,
        tool_context: Any,
    ) -> Any:
        try:
            trace_id = (
                getattr(tool_context, "trace_id", None)
                or current_trace_id()
                or str(uuid.uuid4())
            )
            handoff_target = self._owner._consume_handoff_signal(
                target_agent="scheduling",
                execution_mode="inline",
                reason="router_scheduling",
                context_hint=str(message or "")[:160],
            )
            handoff_request = self._owner._build_handoff_request(
                target_agent=handoff_target,
                message=message,
                user_id=user_id,
                execution_mode="inline",
                intent="scheduling",
                tool_context=tool_context,
                handoff_reason="router_scheduling",
            )
            handoff_result = await self._owner._handoff_manager.delegate(handoff_request)

            if handoff_result.status == "needs_followup":
                followup_payload = dict(handoff_result.structured_payload or {})
                followup_text = (
                    str(handoff_result.user_visible_text or "").strip()
                    or str(followup_payload.get("clarification") or "").strip()
                    or "When would you like to be reminded?"
                )
                return self._owner._tag_response_with_routing_type(
                    ResponseFormatter.build_response(
                        display_text=followup_text,
                        voice_text=followup_text,
                        mode="normal",
                        confidence=0.8,
                        structured_data={"_scheduling_followup": followup_payload},
                    ),
                    "direct_action",
                )

            if handoff_result.status in {"failed", "rejected"}:
                return self._owner._tag_response_with_routing_type(
                    ResponseFormatter.build_response("I need a clearer scheduling instruction."),
                    "direct_action",
                )

            scheduling_payload = dict(handoff_result.structured_payload or {})
            tool_name = str(scheduling_payload.get("tool_name") or "").strip()
            tool_args = dict(scheduling_payload.get("parameters") or {})
            tool_result, invocation = await self._owner._execute_tool_call(
                tool_name,
                tool_args,
                user_id,
                tool_context=tool_context,
            )
            summary_text = (
                str(scheduling_payload.get("confirmation_text") or "").strip()
                if invocation.status == "success" and str(scheduling_payload.get("confirmation_text") or "").strip()
                else str(tool_result.get("message") or "").strip()
                or str(tool_result.get("result") or "").strip()
                or "I was unable to complete that."
            )
            logger.info(
                "scheduling_result action_type=%s tool_name=%s status=%s",
                str(scheduling_payload.get("action_type") or ""),
                tool_name,
                invocation.status,
            )
            response = ResponseFormatter.build_response(
                display_text=summary_text,
                voice_text=summary_text,
                mode="normal",
                confidence=0.9 if invocation.status == "success" else 0.5,
                structured_data={
                    "_scheduling_result": {
                        **scheduling_payload,
                        "tool_status": invocation.status,
                        "tool_result": tool_result,
                        "trace_id": str(scheduling_payload.get("trace_id") or trace_id),
                    }
                },
            )
            self._owner.turn_state["pending_system_action_result"] = summary_text
            return self._owner._tag_response_with_routing_type(response, "direct_action")
        except Exception as e:
            logger.error("scheduling_route_failed error=%s", e, exc_info=True)
            return self._owner._tag_response_with_routing_type(
                ResponseFormatter.build_response("I was unable to complete that."),
                "direct_action",
            )
