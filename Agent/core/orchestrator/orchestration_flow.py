"""Orchestration spine mixin for AgentOrchestrator."""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from core.orchestrator.onboarding import (
    build_onboarding_system_note,
    extract_onboarding_prefs,
    is_onboarding_complete,
)
from core.orchestrator.turn_context import TurnContext
from core.observability.trace_context import start_trace
from core.response.agent_response import AgentResponse
from core.response.response_formatter import ResponseFormatter
from core.utils.intent_utils import normalize_intent

logger = logging.getLogger(__name__)


class OrchestrationFlow:
    async def _maybe_capture_onboarding_prefs(self, message: str, user_id: str) -> None:
        pref_manager = getattr(self, "_preference_manager", None) or self.preference_manager
        if not pref_manager:
            return
        try:
            get_all = getattr(pref_manager, "get_all", None)
            prefs = await get_all(user_id or "") if callable(get_all) else {}
            if not is_onboarding_complete(prefs):
                extracted = extract_onboarding_prefs(message)
                if extracted:
                    for key, value in extracted.items():
                        await pref_manager.set(user_id or "", key, value)
                    logger.info(
                        "onboarding_prefs_captured user_id=%s keys=%s",
                        user_id,
                        list(extracted.keys()),
                    )
                else:
                    logger.info(
                        "onboarding_prompt_needed user_id=%s note=%s",
                        user_id,
                        build_onboarding_system_note()[:120],
                    )
        except Exception as onboarding_err:
            logger.warning("onboarding_check_failed error=%s", onboarding_err)

    def _finalize_turn_response(
        self,
        *,
        turn_ctx: TurnContext,
        response: AgentResponse,
        turn_start: float,
        route_hint: str = "",
    ) -> AgentResponse:
        self._queue_outcome_log(
            turn_ctx=turn_ctx,
            response=response,
            turn_start=turn_start,
            route_hint=route_hint,
        )
        return response

    def _queue_outcome_log(
        self,
        *,
        turn_ctx: TurnContext,
        response: AgentResponse,
        turn_start: float,
        route_hint: str = "",
    ) -> None:
        outcome_logger = getattr(self, "_outcome_logger", None)
        if outcome_logger is None or response is None:
            return

        try:
            from core.rl import TaskOutcome

            route = str(
                route_hint
                or (response.structured_data or {}).get("_routing_mode_type")
                or turn_ctx.route
                or "chat"
            ).strip().lower()
            tool_calls = []
            for invocation in getattr(response, "tool_invocations", None) or []:
                tool_name = str(getattr(invocation, "tool_name", "")).strip()
                if tool_name:
                    tool_calls.append(tool_name)

            latency_ms = max(0.0, (time.monotonic() - turn_start) * 1000.0)
            outcome = TaskOutcome(
                task_id=str(turn_ctx.turn_id or self.turn_state.get("current_turn_id") or ""),
                agent_type=route or "chat",
                prompt=str(turn_ctx.message or ""),
                response=str(getattr(response, "display_text", "") or ""),
                success=bool(str(getattr(response, "display_text", "") or "").strip()),
                route=route or "chat",
                latency_ms=latency_ms,
                tool_calls=tool_calls,
                session_id=str(turn_ctx.session_id or self._current_session_id or ""),
                user_id=str(turn_ctx.user_id or ""),
            )
            asyncio.create_task(outcome_logger.log(outcome))
        except Exception as exc:
            logger.debug("outcome_log_queue_failed turn_id=%s error=%s", turn_ctx.turn_id, exc)

    async def handle_message(
        self,
        message: str,
        user_id: str,
        tool_context: Any = None,
        origin: str = "chat",
    ) -> AgentResponse:
        """
        Handle incoming user message with Intent-Based Routing.

        Routing Logic:
        1. Check active task -> If running, route to Worker/Planner (via TaskManager)
        2. If no active task -> Analyze Intent
            - Casual/Greeting -> CHAT Role
            - Task Request -> PLANNER Role
        """
        normalized_origin = str(origin or "").strip().lower()
        turn_ctx = TurnContext.from_handle_message_args(
            message=message,
            user_id=user_id,
            tool_context=tool_context,
            origin=normalized_origin,
        )
        turn_started_at = time.monotonic()
        logger.debug(
            "turn_context_created turn_id=%s origin=%s session_id=%s",
            turn_ctx.turn_id,
            turn_ctx.origin,
            turn_ctx.session_id,
        )
        if normalized_origin == "voice":
            normalized_message, message_changed = self._normalize_voice_transcription_for_routing(message)
            if message_changed:
                logger.info(
                    "voice_transcription_normalized original=%s normalized=%s",
                    str(message or "")[:120],
                    normalized_message[:120],
                )
                message = normalized_message

        session_id = getattr(getattr(self, "room", None), "name", None) or "console_session"
        active_session_id = getattr(tool_context, "session_id", None) or session_id
        effective_message = self._augment_message_with_session_bootstrap(message, active_session_id)
        self._update_turn_identity(user_id=user_id, session_id=active_session_id)
        incoming_turn_id = getattr(tool_context, "turn_id", None) if tool_context is not None else None
        self._start_new_turn(message, turn_id=incoming_turn_id)
        trace_ctx = start_trace(session_id=session_id, user_id=user_id)
        logger.info(
            f"🔥 ORCHESTRATOR RECEIVED MESSAGE from {user_id} "
            f"(trace_id={trace_ctx.get('trace_id')}, session_id={session_id})"
        )

        try:
            if self.context_guard:
                if self.context_guard.count_tokens(message) > 2000:
                    msg = "I'm sorry, that request is too long for me to process safely."
                    await self._announce(msg)
                    response = ResponseFormatter.build_response(msg, mode="safe")
                    return self._finalize_turn_response(
                        turn_ctx=turn_ctx,
                        response=response,
                        turn_start=turn_started_at,
                        route_hint="guard",
                    )

            if self._is_malformed_short_request(message):
                response = ResponseFormatter.build_response(
                    "I can help with tasks, reminders, notes, or calendar events. "
                    "Please rephrase your request in one simple sentence."
                )
                return self._finalize_turn_response(
                    turn_ctx=turn_ctx,
                    response=response,
                    turn_start=turn_started_at,
                    route_hint="guard",
                )

            if not self.enable_task_pipeline:
                await self._maybe_capture_onboarding_prefs(message, user_id)
                response = await self._handle_chat_response(
                    effective_message,
                    user_id,
                    tool_context=tool_context,
                    origin=origin,
                )
                return self._finalize_turn_response(
                    turn_ctx=turn_ctx,
                    response=response,
                    turn_start=turn_started_at,
                )

            active_tasks = await self._maybe_await(self.task_store.get_active_tasks(user_id))
            if active_tasks:
                logger.info(f"🔄 Active task found for {user_id}: {len(active_tasks)}")
                if any(k in message.lower() for k in ("status", "progress", "how far", "done")):
                    first = active_tasks[0]
                    total_steps = max(len(first.steps), 1)
                    current_step_display = min(first.current_step_index + 1, total_steps)
                    response = ResponseFormatter.build_response(
                        f"You have {len(active_tasks)} active task(s). "
                        f"Current: '{first.title}' step {current_step_display}/{total_steps}."
                    )
                    return self._finalize_turn_response(
                        turn_ctx=turn_ctx,
                        response=response,
                        turn_start=turn_started_at,
                        route_hint="task",
                    )

            message_lower = (message or "").lower()
            direct_tool_intent = self._detect_direct_tool_intent(message, origin=origin)
            scheduling_domain_request = any(
                kw in message_lower
                for kw in [
                    "remind me",
                    "set reminder",
                    "set a reminder",
                    "list reminders",
                    "show reminders",
                    "delete reminder",
                    "set alarm",
                    "set an alarm",
                    "list alarms",
                    "show alarms",
                    "delete alarm",
                    "calendar event",
                    "calendar events",
                ]
            )
            explicit_task_trigger = any(
                kw in message_lower
                for kw in [
                    "create task",
                    "new task",
                    "make a plan",
                    "plan this",
                    "multi step",
                    "step by step",
                    "workflow",
                ]
            )
            report_export_trigger = self._is_report_export_request(message_lower)
            is_task_request = explicit_task_trigger or (
                not scheduling_domain_request
                and direct_tool_intent is None
                and any(
                    kw in message_lower
                    for kw in [
                        "create ",
                        "todo",
                        "to-do",
                    ]
                )
            )
            if not is_task_request and not scheduling_domain_request and direct_tool_intent is None:
                is_task_request = self._is_multi_step_task_request(message_lower)
            if not is_task_request and report_export_trigger:
                is_task_request = True

            intent_str = normalize_intent("TASK REQUEST" if is_task_request else "CASUAL CHAT")
            logger.info(f"🔀 Intent: {intent_str} -> Routing...")

            if is_task_request:
                task_response = await self._handle_task_request(
                    effective_message,
                    user_id,
                    tool_context=tool_context,
                )
                response = ResponseFormatter.normalize_response(task_response, mode="planning")
                if hasattr(self.agent, "smart_llm"):
                    from core.llm.role_llm import RoleLLM

                    role_llm = RoleLLM(self.agent.smart_llm)
                    voice_candidate = await self._generate_voice_text(role_llm, response.display_text)
                    response = ResponseFormatter.build_response(
                        display_text=response.display_text,
                        voice_text=voice_candidate or response.voice_text,
                        sources=response.sources,
                        tool_invocations=response.tool_invocations,
                        mode=response.mode,
                        memory_updated=response.memory_updated,
                        confidence=response.confidence,
                        structured_data=response.structured_data,
                    )
                self._append_conversation_history("user", message, source="history")
                assistant_source = "task_step"
                if getattr(response, "tool_invocations", None):
                    assistant_source = "tool_output"
                self._append_conversation_history(
                    "assistant",
                    response.display_text,
                    source=assistant_source,
                )
                return self._finalize_turn_response(
                    turn_ctx=turn_ctx,
                    response=response,
                    turn_start=turn_started_at,
                    route_hint="task",
                )

            await self._maybe_capture_onboarding_prefs(message, user_id)
            response = await self._handle_chat_response(
                effective_message,
                user_id,
                tool_context=tool_context,
                origin=origin,
            )
            self._append_conversation_history("user", message, source="history")
            assistant_source = "history"
            routing_mode = str((response.structured_data or {}).get("_routing_mode_type") or "").strip().lower()
            if routing_mode in {"direct_action", "fast_path"}:
                assistant_source = "direct_action"
            elif getattr(response, "tool_invocations", None):
                assistant_source = "tool_output"
            self._append_conversation_history(
                "assistant",
                response.display_text,
                source=assistant_source,
            )
            return self._finalize_turn_response(
                turn_ctx=turn_ctx,
                response=response,
                turn_start=turn_started_at,
            )

        except Exception as e:
            logger.error(f"❌ Error handling message: {e}")
            response = ResponseFormatter.build_response("Something went wrong processing your request.")
            return self._finalize_turn_response(
                turn_ctx=turn_ctx,
                response=response,
                turn_start=turn_started_at,
                route_hint="error",
            )
