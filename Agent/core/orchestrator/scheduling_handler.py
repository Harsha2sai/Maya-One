"""
SchedulingHandler - Handles scheduling route execution.
Extracted from ChatResponseMixin (Phase 24).
"""
from __future__ import annotations

import logging
import re
import time
import uuid
from typing import Any

from core.observability.trace_context import current_trace_id
from core.response.response_formatter import ResponseFormatter
from core.telemetry.runtime_metrics import RuntimeMetrics

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
            normalized_message = str(message or "").strip()
            lowered_message = normalized_message.lower()
            trace_id = (
                getattr(tool_context, "trace_id", None)
                or current_trace_id()
                or str(uuid.uuid4())
            )
            pending_action: dict[str, Any] | None = None
            pending_reason = "no_state"
            action_state_enabled = getattr(self._owner, "_action_state_enabled", False) is True
            pending_getter = getattr(self._owner, "_get_pending_scheduling_action_with_reason_for_context", None)
            pending_setter = getattr(self._owner, "_set_pending_scheduling_action_for_context", None)
            pending_clearer = getattr(self._owner, "_clear_pending_scheduling_action_for_context", None)
            if action_state_enabled and callable(pending_getter):
                pending_result = pending_getter(tool_context)
                if isinstance(pending_result, tuple) and len(pending_result) == 2:
                    pending_action, pending_reason = pending_result
                if pending_action is None and pending_reason in {"expired_ttl", "expired_turns"}:
                    RuntimeMetrics.increment("pending_scheduling_expired_total")
                if pending_action and self._is_scheduling_cancellation(lowered_message):
                    if callable(pending_clearer):
                        pending_clearer(tool_context)
                    cancel_text = "Okay, I canceled that reminder setup."
                    return self._owner._tag_response_with_routing_type(
                        ResponseFormatter.build_response(
                            display_text=cancel_text,
                            voice_text=cancel_text,
                            mode="normal",
                            confidence=0.9,
                            structured_data={
                                "_scheduling_followup": {
                                    "status": "canceled",
                                    "reason": "user_canceled_pending_setup",
                                }
                            },
                        ),
                        "direct_action",
                    )
                if pending_action and self._is_explicit_new_scheduling_command(lowered_message):
                    if callable(pending_clearer):
                        pending_clearer(tool_context)
                    pending_action = None
                elif pending_action and self._looks_like_reminder_task_followup(lowered_message):
                    pending_data = pending_action.get("data") if isinstance(pending_action.get("data"), dict) else {}
                    pending_time = str(pending_data.get("time") or "").strip()
                    if pending_time:
                        normalized_message = f"set a reminder to {normalized_message} {pending_time}"
                        lowered_message = normalized_message.lower()
                        RuntimeMetrics.increment("pending_scheduling_resume_total")
                        logger.info(
                            "pending_scheduling_resume session=%s task=%s time=%s",
                            self._owner._session_key_for_context(tool_context),
                            str(message or "")[:80],
                            pending_time,
                        )

            handoff_target = self._owner._consume_handoff_signal(
                target_agent="scheduling",
                execution_mode="inline",
                reason="router_scheduling",
                context_hint=normalized_message[:160],
            )
            handoff_request = self._owner._build_handoff_request(
                target_agent=handoff_target,
                message=normalized_message,
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
                RuntimeMetrics.increment("scheduling_clarification_requested")
                if (
                    str(followup_payload.get("action_type") or "").strip().lower() == "set_reminder"
                    and str(followup_payload.get("missing_slot") or "").strip().lower() == "task"
                ):
                    reminder_time = str((followup_payload.get("parameters") or {}).get("time") or "").strip()
                    if reminder_time:
                        pending_payload = {
                            "type": "set_reminder",
                            "domain": "scheduling",
                            "data": {"time": reminder_time},
                            "summary": f"Pending reminder at {reminder_time}",
                            "written_at_ts": time.time(),
                            "written_at_turn": int(self._owner._current_action_state_turn(tool_context)),
                        }
                        state_written = False
                        if callable(pending_setter):
                            state_written = bool(
                                pending_setter(
                                    action=pending_payload,
                                    tool_context=tool_context,
                                )
                            )
                        if state_written:
                            RuntimeMetrics.increment("scheduling_missing_task_followup_total")
                            logger.info(
                                "pending_scheduling_written session=%s time=%s",
                                self._owner._session_key_for_context(tool_context),
                                reminder_time,
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
                if pending_action:
                    RuntimeMetrics.increment("scheduling_clarification_requested")
                    reminder_text = "What should I remind you about?"
                    return self._owner._tag_response_with_routing_type(
                        ResponseFormatter.build_response(
                            display_text=reminder_text,
                            voice_text=reminder_text,
                            mode="normal",
                            confidence=0.85,
                            structured_data={
                                "_scheduling_followup": {
                                    "status": "needs_followup",
                                    "clarification": reminder_text,
                                    "reason": "pending_reminder_requires_task",
                                }
                            },
                        ),
                        "direct_action",
                    )
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
            if (
                invocation.status == "success"
                and str(scheduling_payload.get("action_type") or "").strip().lower() == "set_reminder"
            ):
                if callable(pending_clearer):
                    pending_clearer(tool_context)
                params = scheduling_payload.get("parameters")
                if not isinstance(params, dict):
                    params = {}
                task_text = str(params.get("text") or "").strip()
                reminder_time = str(params.get("time") or "").strip()
                action_payload = {
                    "type": "set_reminder",
                    "domain": "scheduling",
                    "summary": summary_text,
                    "data": {
                        "task": task_text,
                        "time": reminder_time,
                    },
                    "written_at_ts": time.time(),
                    "written_at_turn": int(self._owner._current_action_state_turn(tool_context)),
                }
                state_written = self._owner._set_last_action_for_context(
                    action=action_payload,
                    tool_context=tool_context,
                )
                if state_written:
                    session_key = self._owner._session_key_for_context(tool_context)
                    logger.info(
                        "last_action_written type=set_reminder session=%s",
                        session_key,
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

    @staticmethod
    def _is_explicit_new_scheduling_command(text: str) -> bool:
        return bool(
            re.search(
                r"\b(remind me to|set (?:a )?reminder|list reminders|show reminders|delete reminder|set (?:an )?alarm|list alarms|show alarms|calendar event)\b",
                str(text or ""),
            )
        )

    @staticmethod
    def _is_scheduling_cancellation(text: str) -> bool:
        return bool(
            re.search(
                r"\b(cancel|never mind|nevermind|stop|forget it|don(?:'|’)t remind)\b",
                str(text or ""),
            )
        )

    @staticmethod
    def _looks_like_reminder_task_followup(text: str) -> bool:
        sample = str(text or "").strip()
        if not sample:
            return False
        if re.search(r"[?]", sample):
            return False
        # Guardrail: avoid treating conversational follow-ups as reminder task text.
        if re.search(r"\b(what|when|who|why|how|which|tell|about|him|her|them|his|hers|their)\b", sample, re.IGNORECASE):
            return False
        if SchedulingHandler._is_explicit_new_scheduling_command(sample):
            return False
        if re.search(r"\b(time|date|weather|who are you|what is your name|search|open)\b", sample):
            return False
        words = re.findall(r"\b[\w'-]+\b", sample)
        return 1 <= len(words) <= 8
