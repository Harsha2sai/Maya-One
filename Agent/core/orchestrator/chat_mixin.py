"""Chat response serialization and execution mixin for AgentOrchestrator."""
from __future__ import annotations

import asyncio
import logging
import re
import time
import uuid
from collections import deque
from typing import Any, List

from core.observability.trace_context import current_trace_id
from core.response.agent_response import AgentResponse, ToolInvocation
from core.response.response_formatter import ResponseFormatter
from core.security.input_guard import InputGuard

logger = logging.getLogger(__name__)


class ChatResponseMixin:
    async def _handle_chat_response(
        self,
        message: str,
        user_id: str,
        tool_context: Any = None,
        origin: str = "chat",
    ) -> AgentResponse:
        """Serialize per-session chat handling to prevent concurrent dispatch races."""
        session_key = self._resolve_session_queue_key(tool_context)
        lock = self._session_locks.setdefault(session_key, asyncio.Lock())
        queue = self._session_queues.setdefault(session_key, deque())

        loop = asyncio.get_running_loop()
        result_future: asyncio.Future[AgentResponse] = loop.create_future()
        queue.append((message, user_id, tool_context, origin, result_future))

        if len(queue) > self._session_queue_limit:
            dropped_message, _, _, _, dropped_future = queue.popleft()
            if not dropped_future.done():
                dropped_future.set_result(self._queue_rejection_response())
            logger.warning(
                "dropped_utterance session_id=%s queue_depth=%s dropped_preview=%s",
                session_key,
                len(queue),
                str(dropped_message or "")[:80],
            )

        if not lock.locked():
            async with lock:
                while queue:
                    queued_message, queued_user_id, queued_tool_ctx, queued_origin, queued_future = queue.popleft()
                    if queued_future.done():
                        continue
                    try:
                        response = await self._handle_chat_response_core(
                            queued_message,
                            queued_user_id,
                            tool_context=queued_tool_ctx,
                            origin=queued_origin,
                        )
                    except Exception as e:
                        logger.error("session_queue_dispatch_failed session_id=%s error=%s", session_key, e, exc_info=True)
                        response = self._tag_response_with_routing_type(
                            ResponseFormatter.build_response(
                                "Something went wrong processing your request."
                            ),
                            "informational",
                        )
                    queued_session_id = (
                        getattr(queued_tool_ctx, "session_id", None)
                        or session_key
                    )
                    await self._store_chat_turn_memory(
                        queued_message,
                        response,
                        user_id=queued_user_id,
                        session_id=queued_session_id,
                        origin=queued_origin,
                    )
                    if not queued_future.done():
                        queued_future.set_result(response)

        return await result_future

    async def _handle_chat_response_core(
        self,
        message: str,
        user_id: str,
        tool_context: Any = None,
        origin: str = "chat",
    ) -> AgentResponse:
        """Execute Casual Chat flow using CHAT role."""
        from core.llm.llm_roles import LLMRole
        from core.llm.role_llm import RoleLLM

        message = InputGuard.sanitize(message)
        if not message:
            return self._tag_response_with_routing_type(
                ResponseFormatter.build_response("I didn't catch that."),
                "informational",
            )

        fast_path_input = self._extract_user_message_segment(message) or message
        direct_tool = self._detect_direct_tool_intent(fast_path_input, origin=origin)
        if direct_tool:
            tool_name, tool_args = direct_tool.tool, direct_tool.args
            logger.info(
                "🧭 routing_mode=deterministic_fast_path fast_path_intent=%s fast_path_group=%s planner_skipped=true synthesis_skipped=true origin=%s",
                tool_name or "none",
                direct_tool.group,
                origin,
            )
            if not tool_name:
                response = ResponseFormatter.build_response(
                    display_text=direct_tool.template,
                    voice_text=direct_tool.template,
                    mode="direct",
                    structured_data={"_direct_group": direct_tool.group},
                )
                self.turn_state["pending_tool_result_text"] = direct_tool.template
                return self._tag_response_with_routing_type(response, "fast_path")
            if (
                tool_name == "run_shell_command"
                and isinstance(tool_args.get("commands"), list)
                and tool_args.get("commands")
            ):
                commands = [str(cmd).strip() for cmd in tool_args.get("commands", []) if str(cmd).strip()]
                tool_invocations: List[ToolInvocation] = []
                outputs: List[str] = []
                for command in commands:
                    shell_output, shell_invocation = await self._execute_tool_call(
                        tool_name="run_shell_command",
                        args={"command": command},
                        user_id=user_id,
                        tool_context=tool_context,
                    )
                    tool_invocations.append(shell_invocation)
                    if isinstance(shell_output, dict):
                        outputs.append(
                            str(shell_output.get("result") or shell_output.get("message") or "").strip()
                        )
                    else:
                        outputs.append(str(shell_output or "").strip())

                response = ResponseFormatter.build_response(
                    display_text=direct_tool.template,
                    voice_text=direct_tool.template,
                    tool_invocations=tool_invocations,
                    mode="direct",
                    structured_data={
                        "commands": commands,
                        "results": outputs,
                    },
                )
                self.turn_state["pending_tool_result_text"] = direct_tool.template
                return self._tag_response_with_routing_type(response, "fast_path")
            tool_output, tool_invocation = await self._execute_tool_call(
                tool_name=tool_name,
                args=tool_args,
                user_id=user_id,
                tool_context=tool_context,
            )
            structured_data = tool_output if isinstance(tool_output, dict) else {"result": str(tool_output)}
            display_candidate = ResponseFormatter.extract_display_candidate(structured_data, tool_name)
            output_text = str(
                structured_data.get("result")
                or structured_data.get("message")
                or tool_output
                or ""
            ).strip()
            output_text_l = output_text.lower()
            voice_text = direct_tool.template
            if structured_data.get("success") is False:
                safe_failure = str(structured_data.get("message") or "I was unable to complete that.").strip()
                response = ResponseFormatter.build_response(
                    display_text=safe_failure,
                    voice_text=safe_failure,
                    tool_invocations=[tool_invocation],
                    mode="direct",
                    structured_data=structured_data,
                )
                self.turn_state["pending_tool_result_text"] = safe_failure
                return self._tag_response_with_routing_type(response, "fast_path")
            if tool_name == "get_weather":
                if output_text and "couldn't fetch weather" in output_text_l:
                    voice_text = output_text
                elif output_text and ("error occurred while retrieving weather" in output_text_l):
                    voice_text = (
                        "I couldn't fetch weather right now. Please try again in a moment."
                    )
                elif output_text and ("could not retrieve weather" in output_text_l):
                    voice_text = (
                        "I couldn't fetch weather right now. Please try again in a moment."
                    )
                elif output_text:
                    voice_text = output_text
                elif display_candidate:
                    voice_text = display_candidate
            elif tool_name == "web_search" and isinstance(structured_data, dict):
                if structured_data.get("error") == "timeout":
                    voice_text = "Search timed out. Please try again."
                elif structured_data.get("error") == "search_unavailable":
                    voice_text = "Search is unavailable right now."
                elif display_candidate:
                    voice_text = display_candidate
            elif tool_name in {"get_time", "get_date", "get_current_datetime"}:
                temporal_value = str(
                    structured_data.get("result")
                    or structured_data.get("time")
                    or structured_data.get("date")
                    or structured_data.get("datetime")
                    or ""
                ).strip()
                if display_candidate:
                    voice_text = display_candidate
                elif temporal_value:
                    cleaned_value = temporal_value if temporal_value.endswith(".") else f"{temporal_value}."
                    if tool_name == "get_time" and "time" not in temporal_value.lower():
                        voice_text = f"The current time is {cleaned_value}"
                    elif tool_name == "get_date" and not re.search(r"\b(today|date)\b", temporal_value, re.IGNORECASE):
                        voice_text = f"Today's date is {cleaned_value}"
                    else:
                        voice_text = cleaned_value
            self._capture_implicit_preference_from_direct_tool(
                tool_name=tool_name,
                tool_args=tool_args,
                user_id=user_id,
            )

            response = ResponseFormatter.build_response(
                display_text=display_candidate or voice_text,
                voice_text=voice_text,
                tool_invocations=[tool_invocation],
                mode="direct",
                structured_data=structured_data,
            )
            self.turn_state["pending_tool_result_text"] = str(voice_text or "")
            return self._tag_response_with_routing_type(response, "fast_path")

        small_talk_response = self._match_small_talk_fast_path(message)
        if small_talk_response:
            logger.info("small_talk_fast_path_matched origin=%s", origin)
            response = ResponseFormatter.build_response(
                display_text=small_talk_response,
                voice_text=small_talk_response,
            )
            return self._tag_response_with_routing_type(response, "informational")

        routing_text = self._extract_user_message_segment(message) or message
        chat_ctx_messages = self._chat_ctx_messages(getattr(self.agent, "chat_ctx", None))
        if self._is_voice_continuation_fragment(
            routing_text=routing_text,
            origin=origin,
            chat_ctx_messages=chat_ctx_messages,
        ):
            logger.info(
                "short_turn_blocked reason=continuation_fragment origin=%s text=%s",
                origin,
                str(routing_text or "")[:120],
            )
            clarification = "Please continue your request so I can handle it correctly."
            return self._tag_response_with_routing_type(
                ResponseFormatter.build_response(
                    display_text=clarification,
                    voice_text=clarification,
                ),
                "informational",
            )

        if self._is_report_export_request(routing_text):
            logger.info(
                "document_export_intent_bypasses_pronoun_rewrite text=%s",
                routing_text[:120],
            )
            rewritten_followup, forced_research, ambiguous_followup = routing_text, False, False
        else:
            rewritten_followup, forced_research, ambiguous_followup = self._rewrite_pronoun_followup_pre_router(
                routing_text,
                tool_context=tool_context,
            )
        if ambiguous_followup:
            logger.info(
                "research_pronoun_override forced=false ambiguous=true rewritten=%s",
                rewritten_followup[:120],
            )
            clarification = "Could you clarify who you mean before I research that?"
            return self._tag_response_with_routing_type(
                ResponseFormatter.build_response(
                    display_text=clarification,
                    voice_text=clarification,
                ),
                "informational",
            )
        if forced_research:
            logger.info(
                "research_pronoun_override forced=true ambiguous=false rewritten=%s",
                rewritten_followup[:120],
            )
            return await self._handle_research_route(
                message=rewritten_followup,
                user_id=user_id,
                tool_context=tool_context,
                query_rewritten=True,
                query_ambiguous=False,
            )

        route_started = time.monotonic()
        agent_key = await self._router.route(routing_text, user_id, chat_ctx=chat_ctx_messages)
        route_elapsed_ms = int(max(0.0, (time.monotonic() - route_started) * 1000.0))
        logger.info(
            "route_decision_timing route=%s elapsed_ms=%s origin=%s",
            agent_key,
            route_elapsed_ms,
            origin,
        )

        if agent_key == "identity":
            return await self._handle_identity_fast_path(
                message=message,
                user_id=user_id,
                origin=origin,
            )

        if agent_key == "media_play":
            try:
                media_command = await self._resolve_media_query_from_preferences(message, user_id)
                session_id = (
                    getattr(tool_context, "session_id", None)
                    or self._current_session_id
                    or getattr(getattr(self, "room", None), "name", None)
                    or "console_session"
                )
                trace_id = (
                    getattr(tool_context, "trace_id", None)
                    or current_trace_id()
                    or str(uuid.uuid4())
                )
                handoff_target = self._consume_handoff_signal(
                    target_agent="media",
                    execution_mode="inline",
                    reason="router_media_play",
                    context_hint=str(message or "")[:160],
                )
                handoff_request = self._build_handoff_request(
                    target_agent=handoff_target,
                    message=media_command,
                    user_id=user_id,
                    execution_mode="inline",
                    intent="media_play",
                    tool_context=tool_context,
                    handoff_reason="router_media_play",
                )
                handoff_result = await self._handoff_manager.delegate(handoff_request)

                if handoff_result.status == "needs_followup":
                    followup_payload = dict(handoff_result.structured_payload or {})
                    if followup_payload.get("url"):
                        await self._publish_runtime_topic_event(
                            "maya/system/spotify/auth_url",
                            {
                                "type": "spotify_auth_url",
                                "platform": str(followup_payload.get("platform") or "desktop"),
                                "url": str(followup_payload.get("url") or ""),
                                "state": str(followup_payload.get("state") or ""),
                                "timestamp": datetime.now(timezone.utc).isoformat(),
                                "source": "orchestrator_media_handoff",
                            },
                        )
                    summary_text = (
                        str(handoff_result.user_visible_text or "").strip()
                        or str(followup_payload.get("message") or "").strip()
                        or "Spotify needs to be connected first."
                    )
                    response = ResponseFormatter.build_response(
                        display_text=summary_text,
                        voice_text=summary_text,
                        mode="normal",
                        confidence=0.7,
                        structured_data={
                            "_media_followup": followup_payload,
                            "_handoff_result": followup_payload,
                        },
                    )
                    logger.info(
                        "media_followup provider=%s requires_auth=%s trace_id=%s",
                        str(followup_payload.get("provider") or "spotify"),
                        bool(followup_payload.get("requires_auth")),
                        trace_id,
                    )
                    return self._tag_response_with_routing_type(response, "direct_action")

                if handoff_result.status in {"failed", "rejected"}:
                    logger.warning(
                        "media_handoff_fallback_to_legacy trace_id=%s status=%s error_code=%s",
                        trace_id,
                        handoff_result.status,
                        handoff_result.error_code,
                    )
                    media_agent = self._resolve_media_agent()
                    media_result = await media_agent.run(
                        command=media_command,
                        user_id=user_id,
                        session_id=session_id,
                        trace_id=trace_id,
                    )
                    media_payload = {
                        "action": media_result.action,
                        "provider": media_result.provider,
                        "track_name": media_result.track.title if media_result.track else "",
                        "artist": media_result.track.artist if media_result.track else "",
                        "album_art_url": media_result.track.album_art_url if media_result.track else "",
                        "track_url": media_result.track.url if media_result.track else "",
                        "trace_id": trace_id,
                    }
                    summary_text = str(media_result.message or "").strip() or "I was unable to complete that."
                    structured_data = {"_media_result": media_payload}
                else:
                    media_payload = dict(handoff_result.structured_payload or {})
                    summary_text = (
                        str(handoff_result.user_visible_text or "").strip()
                        or str(media_payload.get("message") or "").strip()
                        or "I was unable to complete that."
                    )
                    structured_data = {
                        "_media_result": {
                            "action": str(media_payload.get("action") or ""),
                            "provider": str(media_payload.get("provider") or ""),
                            "track_name": str(media_payload.get("track_name") or ""),
                            "artist": str(media_payload.get("artist") or ""),
                            "album_art_url": str(media_payload.get("album_art_url") or ""),
                            "track_url": str(media_payload.get("track_url") or ""),
                            "trace_id": str(media_payload.get("trace_id") or trace_id),
                        },
                        "_handoff_result": media_payload,
                    }
                    logger.info(
                        "media_result action=%s provider=%s success=%s",
                        str(media_payload.get("action") or ""),
                        str(media_payload.get("provider") or ""),
                        bool(media_payload.get("success")),
                    )
                response = ResponseFormatter.build_response(
                    display_text=summary_text,
                    voice_text=summary_text,
                    mode="normal",
                    confidence=0.9 if structured_data["_media_result"].get("provider") else 0.5,
                    structured_data=structured_data,
                )
                self.turn_state["pending_system_action_result"] = summary_text
                return self._tag_response_with_routing_type(response, "direct_action")
            except Exception as e:
                logger.error("media_route_failed error=%s", e, exc_info=True)
                return self._tag_response_with_routing_type(
                    ResponseFormatter.build_response("I was unable to complete that."),
                    "direct_action",
                )

        if agent_key == "scheduling":
            try:
                trace_id = (
                    getattr(tool_context, "trace_id", None)
                    or current_trace_id()
                    or str(uuid.uuid4())
                )
                handoff_target = self._consume_handoff_signal(
                    target_agent="scheduling",
                    execution_mode="inline",
                    reason="router_scheduling",
                    context_hint=str(message or "")[:160],
                )
                handoff_request = self._build_handoff_request(
                    target_agent=handoff_target,
                    message=message,
                    user_id=user_id,
                    execution_mode="inline",
                    intent="scheduling",
                    tool_context=tool_context,
                    handoff_reason="router_scheduling",
                )
                handoff_result = await self._handoff_manager.delegate(handoff_request)

                if handoff_result.status == "needs_followup":
                    followup_payload = dict(handoff_result.structured_payload or {})
                    followup_text = (
                        str(handoff_result.user_visible_text or "").strip()
                        or str(followup_payload.get("clarification") or "").strip()
                        or "When would you like to be reminded?"
                    )
                    return self._tag_response_with_routing_type(
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
                    return self._tag_response_with_routing_type(
                        ResponseFormatter.build_response("I need a clearer scheduling instruction."),
                        "direct_action",
                    )

                scheduling_payload = dict(handoff_result.structured_payload or {})
                tool_name = str(scheduling_payload.get("tool_name") or "").strip()
                tool_args = dict(scheduling_payload.get("parameters") or {})
                tool_result, invocation = await self._execute_tool_call(
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
                self.turn_state["pending_system_action_result"] = summary_text
                return self._tag_response_with_routing_type(response, "direct_action")
            except Exception as e:
                logger.error("scheduling_route_failed error=%s", e, exc_info=True)
                return self._tag_response_with_routing_type(
                    ResponseFormatter.build_response("I was unable to complete that."),
                    "direct_action",
                )

        if agent_key == "research":
            research_query = (self._extract_user_message_segment(message) or message).strip()
            research_word_count = len(re.findall(r"\b[\w'-]+\b", research_query))
            min_research_words = 4 if str(origin or "").strip().lower() == "voice" else 3
            if research_word_count < min_research_words:
                if min_research_words == 4:
                    logger.info(
                        "research_route_blocked_short_voice_turn words=%s min_words=%s query=%s",
                        research_word_count,
                        min_research_words,
                        research_query[:80],
                    )
                else:
                    logger.info(
                        "research_route_guard_short_utterance words=%s query=%s",
                        research_word_count,
                        research_query[:80],
                    )
                agent_key = "chat"
            elif str(origin or "").strip().lower() == "voice" and not re.search(
                r"[.?!]|\b(search|find|lookup|look up|news|latest|current|today)\b",
                research_query,
                flags=re.IGNORECASE,
            ):
                logger.info(
                    "research_route_blocked_low_signal words=%s query=%s",
                    research_word_count,
                    research_query[:80],
                )
                agent_key = "chat"
            else:
                rewritten_query, query_rewritten, query_ambiguous = self.rewrite_research_query_for_context(
                    research_query,
                    tool_context=tool_context,
                )
                logger.info(
                    "research_query_rewritten=%s research_query_ambiguous=%s rewritten_query_preview=%s",
                    query_rewritten,
                    query_ambiguous,
                    rewritten_query[:120],
                )
                if query_ambiguous:
                    clarification = "Could you clarify who you mean before I research that?"
                    return self._tag_response_with_routing_type(
                        ResponseFormatter.build_response(
                            display_text=clarification,
                            voice_text=clarification,
                        ),
                        "informational",
                    )
                return await self._handle_research_route(
                    message=rewritten_query,
                    user_id=user_id,
                    tool_context=tool_context,
                    query_rewritten=query_rewritten,
                    query_ambiguous=query_ambiguous,
                )

        if agent_key == "system":
            try:
                host_profile = self._get_host_capability_profile(refresh=True)
                session_id = (
                    getattr(tool_context, "session_id", None)
                    or self._current_session_id
                    or getattr(getattr(self, "room", None), "name", None)
                    or "console_session"
                )
                trace_id = (
                    getattr(tool_context, "trace_id", None)
                    or current_trace_id()
                    or str(uuid.uuid4())
                )
                handoff_target = self._consume_handoff_signal(
                    target_agent="system_operator",
                    execution_mode="inline",
                    reason="system_route_selected",
                    context_hint=str(message or "")[:160],
                )
                handoff_request = self._build_handoff_request(
                    target_agent=handoff_target,
                    message=message,
                    user_id=user_id,
                    execution_mode="inline",
                    tool_context=tool_context,
                    handoff_reason="system_route_selected",
                    host_profile=host_profile,
                )
                handoff_result = await self._handoff_manager.delegate(handoff_request)
                if handoff_result.status == "completed":
                    tool_name = str((handoff_result.structured_payload or {}).get("tool_name") or "").strip()
                    tool_args = (handoff_result.structured_payload or {}).get("parameters") or {}
                    if tool_name in {"run_shell_command", "cancel_task", "send_email"}:
                        tool_output, tool_invocation = await self._execute_tool_call(
                            tool_name=tool_name,
                            args=tool_args,
                            user_id=user_id,
                            tool_context=tool_context,
                        )
                        structured_data = (
                            tool_output
                            if isinstance(tool_output, dict)
                            else {"result": str(tool_output or "")}
                        )
                        display_text = ResponseFormatter.extract_display_candidate(structured_data, tool_name)
                        output_text = str(
                            structured_data.get("result")
                            or structured_data.get("message")
                            or tool_output
                            or ""
                        ).strip()
                        response = ResponseFormatter.build_response(
                            display_text=display_text or output_text or "Request processed.",
                            voice_text=display_text or output_text or "Request processed.",
                            tool_invocations=[tool_invocation],
                            mode="direct",
                            structured_data={
                                "_handoff_result": handoff_result.structured_payload,
                            },
                        )
                        self.turn_state["pending_system_action_result"] = str(output_text or "")
                        return self._tag_response_with_routing_type(response, "direct_action")
                if handoff_result.status in {"failed", "rejected"}:
                    logger.warning(
                        "system_handoff_fallback_to_legacy trace_id=%s status=%s error_code=%s",
                        trace_id,
                        handoff_result.status,
                        handoff_result.error_code,
                    )
                system_agent = self._resolve_system_agent()

                async def _publish_confirmation_required(action: Any, _session: Any) -> None:
                    if not self.room:
                        return
                    from core.communication import publish_confirmation_required

                    description = str(action.params.get("path") or action.params.get("pid_or_name") or action.action_type.value)
                    await publish_confirmation_required(
                        self.room,
                        action_type=action.action_type.value,
                        description=description,
                        destructive=bool(action.destructive),
                        timeout_seconds=30,
                        trace_id=trace_id,
                    )

                system_result = await system_agent.run(
                    intent=message,
                    user_id=user_id,
                    session_id=session_id,
                    session=self.room,
                    trace_id=trace_id,
                    publish_confirmation_required=_publish_confirmation_required,
                )
                structured_data = {
                    "_system_result": {
                        "action_type": system_result.action_type.value,
                        "success": system_result.success,
                        "message": system_result.message,
                        "detail": system_result.detail,
                        "rollback_available": system_result.rollback_available,
                        "trace_id": system_result.trace_id or trace_id,
                    },
                    "_handoff_result": handoff_result.structured_payload,
                }
                response = ResponseFormatter.build_response(
                    display_text=system_result.message,
                    voice_text=system_result.message,
                    mode="normal",
                    confidence=0.9 if system_result.success else 0.5,
                    structured_data=structured_data,
                )
                self.turn_state["pending_system_action_result"] = str(system_result.message or "")
                return self._tag_response_with_routing_type(response, "direct_action")
            except Exception as e:
                logger.error("system_route_failed error=%s", e, exc_info=True)
                return self._tag_response_with_routing_type(
                    ResponseFormatter.build_response(
                        "Something went wrong with that system action."
                    ),
                    "direct_action",
                )

        history = list(self._conversation_history)
        if agent_key == "chat":
            history = self._filter_chat_history_for_fallthrough(history)
        memory_session_id = (
            getattr(tool_context, "session_id", None)
            or self._current_session_id
            or getattr(getattr(self, "room", None), "name", None)
            or "console_session"
        )

        if not self._is_phase6_context_builder_active():
            logger.warning(
                "phase6_context_builder_disabled origin=%s compare_inline=%s",
                origin,
                self._phase6_context_builder_compare_inline,
            )
            return self._tag_response_with_routing_type(
                ResponseFormatter.build_response(
                    "Context pipeline is temporarily unavailable. Please try again after enabling PHASE6_CONTEXT_BUILDER_ENABLED."
                ),
                "informational",
            )

        from core.llm.llm_roles import CHAT_CONFIG
        from livekit.agents.llm import ChatContext

        retriever = getattr(self.memory, "retriever", None)
        if origin == "voice":
            builder_messages = await self._context_builder.build_for_voice(
                user_message=message,
                user_id=user_id,
                session_id=memory_session_id,
                conversation_history=history,
                system_prompt=CHAT_CONFIG.system_prompt_template,
                retriever=retriever,
            )
        else:
            builder_messages = await self._context_builder.build_for_chat(
                user_message=message,
                user_id=user_id,
                session_id=memory_session_id,
                conversation_history=history,
                system_prompt=CHAT_CONFIG.system_prompt_template,
                retriever=retriever,
                origin=origin,
            )

        has_memory_message = False
        for msg in builder_messages:
            if isinstance(msg, dict):
                src = str(msg.get("source", "")).lower()
                content = str(msg.get("content", ""))
            else:
                src = str(getattr(msg, "source", "")).lower()
                content = str(getattr(msg, "content", ""))
            if src == "memory" or "[memory from previous conversations" in content.lower():
                has_memory_message = True
                break

        if self._is_user_name_recall_query(message) and not has_memory_message:
            fallback_memory = await self._retrieve_memory_context_async(
                message,
                origin=origin,
                routing_mode_type="informational",
                user_id=user_id,
                session_id=memory_session_id,
            )
            if fallback_memory:
                builder_messages.insert(
                    1,
                    {
                        "role": "system",
                        "content": f"[Memory from previous conversations:]\n{fallback_memory}",
                        "source": "memory",
                    },
                )
                logger.info(
                    "memory_context_fallback_injected query_type=user_name_recall origin=%s",
                    origin,
                )

        chat_ctx = ChatContext(builder_messages)
        logger.info(
            "🧩 context_builder_path=phase6 origin=%s messages=%s tokens=%s",
            origin,
            len(builder_messages),
            self._context_message_tokens(builder_messages),
        )

        if self._is_user_name_recall_query(message):
            recalled_name = self._extract_name_from_memory_messages(builder_messages)
            if not recalled_name:
                recalled_name = await self._lookup_profile_name_from_memory(
                    user_id=user_id,
                    session_id=memory_session_id,
                    origin=origin,
                )
            if recalled_name:
                response = ResponseFormatter.build_response(
                    display_text=f"Your name is {recalled_name}.",
                    voice_text=f"Your name is {recalled_name}.",
                    mode="normal",
                    confidence=0.9,
                )
                return self._tag_response_with_routing_type(response, "informational")

        # Use RoleLLM
        # We need access to the underlying LLM. 
        # The Orchestrator doesn't own the LLM directly in __init__, but agent does.
        # But looking at __init__, `agent` is passed. `agent.llm` might not be exposed.
        # `agent` is `Assistant` class. In `agent.py`, `Assistant` has `llm_node` but `smart_llm` is in `entrypoint`.
        # WE NEED ACCESS TO SmartLLM here.
        
        # HACK: The `agent` object passed to Orchestrator likely doesn't have `smart_llm` as a public attribute we can reliably rely on 
        # UNLESS we attach it in `entrypoint`.
        # In `entrypoint`: `agent = ...` then `agent.orchestrator = orchestrator`.
        # The orchestrator is init with `agent`.
        
        # Let's assume we can get it from `self.agent` if we attach it there, OR construct a new one (expensive).
        # Better: Inject `smart_llm` into Orchestrator in `entrypoint`.
        
        # For now, let's look at how we can get LLM.
        # In `entrypoint`, `smart_llm` is created.
        # We should update `entrypoint` to pass `smart_llm` to Orchestrator or attach it to `agent`.
        
        # Assuming `self.agent._llm` or similar is available or we patch `agent.py` to attach it.
        # Let's patch `agent.py` to attach `smart_llm` to `agent` so we can access it here.
        if hasattr(self.agent, "smart_llm"):
             role_llm = RoleLLM(self.agent.smart_llm)
        else:
             # Fallback: Raise error or try to find it
             logger.error("❌ SmartLLM not found on Agent. Chat Role failed.")
             return self._tag_response_with_routing_type(
                 ResponseFormatter.build_response("I'm having trouble connecting to my chat engine."),
                 "informational",
             )
             
        # Phase 1/2: chat tools disabled.
        # Phase 3: reintroduce a safe allowlisted subset of tools.
        chat_tools = self._resolve_phase3_chat_tools()
        if origin == "voice" and chat_tools:
            chat_tools = [
                tool for tool in chat_tools
                if self._tool_name(tool).lower() in self._voice_planner_tools
            ]
            logger.info("voice_tool_subset applied count=%s", len(chat_tools))
        recall_force_toolless = False
        recall_intent = self._is_recall_exclusion_intent(message)
        if recall_intent and chat_tools:
            filtered_tools: List[Any] = []
            for tool in chat_tools:
                name = self._tool_name(tool)
                if name in self.RECALL_EXCLUDED_TOOLS:
                    continue
                filtered_tools.append(tool)
            toolless_recall = self._is_truthy_env(os.getenv("MAYA_RECALL_TOOLLESS", "true"))
            recall_force_toolless = toolless_recall
            chat_tools = [] if toolless_recall else filtered_tools
            logger.info(
                "recall_tool_gate_applied excluded=%s remaining=%s toolless=%s",
                sorted(self.RECALL_EXCLUDED_TOOLS),
                len(chat_tools),
                toolless_recall,
            )
        conversational_toolless = False
        if self._is_conversational_query(message) and not recall_intent:
            conversational_toolless = True
            chat_tools = []
            logger.info(
                "conversational_tool_gate_applied origin=%s reason=small_talk_or_identity",
                origin,
            )
        router_chat_toolless = agent_key == "chat"
        if router_chat_toolless:
            chat_tools = []
            logger.info("router_chat_tool_gate_applied origin=%s reason=chat_dispatch", origin)
        
        def make_chat_call(tools: List[Any]) -> Any:
            kwargs: Dict[str, Any] = {}
            if recall_force_toolless or conversational_toolless or router_chat_toolless:
                kwargs["tool_choice"] = "none"
            if origin == "voice":
                if self._voice_planner_llm_override is None:
                    try:
                        from providers.factory import ProviderFactory

                        self._voice_planner_llm_override = ProviderFactory.get_llm(
                            provider_name=self._voice_llm_provider,
                            model=self._voice_llm_model,
                        )
                    except Exception as e:
                        logger.warning(
                            "voice_planner_model_override_failed provider=%s model=%s error=%s",
                            self._voice_llm_provider,
                            self._voice_llm_model,
                            e,
                        )
                if self._voice_planner_llm_override is not None:
                    kwargs["extra_kwargs"] = {
                        "base_llm_override": self._voice_planner_llm_override,
                    }
            return role_llm.chat(
                role=LLMRole.CHAT,
                chat_ctx=chat_ctx,
                tools=tools,
                **kwargs,
            )

        async def _consume_chat_stream(stream_obj: Any) -> tuple[str, Optional[str], str]:
            full_response_local = ""
            pending_tool_call_local: Optional[str] = None
            pending_args_local = ""
            try:
                async for chunk in stream_obj:
                    delta = ""
                    tool_call_chunk = None

                    # OpenAI/Groq style chunk
                    if hasattr(chunk, "choices") and chunk.choices:
                        choice = chunk.choices[0]
                        delta_obj = getattr(choice, "delta", None)
                        if delta_obj:
                            delta = getattr(delta_obj, "content", "") or ""
                            tc_list = getattr(delta_obj, "tool_calls", None)
                            if tc_list:
                                tool_call_chunk = tc_list[0]
                    # LiveKit-style ChatChunk
                    elif hasattr(chunk, "delta") and chunk.delta:
                        delta_obj = chunk.delta
                        delta = getattr(delta_obj, "content", "") or ""
                        tc_list = getattr(delta_obj, "tool_calls", None)
                        if tc_list:
                            tool_call_chunk = tc_list[0]
                    elif hasattr(chunk, "content"):
                        delta = chunk.content or ""

                    if delta:
                        full_response_local += delta

                    # Capture tool call metadata
                    if tool_call_chunk:
                        t_name = getattr(tool_call_chunk, "name", None)
                        t_args = getattr(tool_call_chunk, "arguments", "") or ""
                        if t_name:
                            pending_tool_call_local = t_name
                            pending_args_local = t_args
                        elif pending_tool_call_local:
                            pending_args_local += t_args
            finally:
                close_fn = getattr(stream_obj, "aclose", None)
                if callable(close_fn):
                    try:
                        await close_fn()
                    except Exception as e:
                        logger.debug(f"⚠️ Failed to close CHAT stream: {e}")

            return full_response_local, pending_tool_call_local, pending_args_local

        async def _run_chat_once(tools: List[Any]) -> tuple[str, Optional[str], str]:
            stream_obj = await make_chat_call(tools)
            return await _consume_chat_stream(stream_obj)

        fallback_error_text = "Sorry, I encountered an issue processing your request. Please try again."
        full_response = ""
        pending_tool_call = None
        pending_args = ""

        try:
            if origin == "voice":
                full_response, pending_tool_call, pending_args = await asyncio.wait_for(
                    _run_chat_once(chat_tools),
                    timeout=self._voice_planner_timeout_s,
                )
            else:
                full_response, pending_tool_call, pending_args = await _run_chat_once(chat_tools)
        except asyncio.TimeoutError:
            logger.warning(
                "planner_timeout timeout_s=%.2f origin=%s",
                self._voice_planner_timeout_s,
                origin,
            )
            fallback = "I'm having trouble right now. Please try again."
            return self._tag_response_with_routing_type(
                ResponseFormatter.build_response(fallback),
                "informational",
            )
        except Exception as e:
            if self._is_tool_call_generation_error(e) and chat_tools:
                logger.warning(f"⚠️ Tool call generation failed, retrying without tools: {e}")
                try:
                    if origin == "voice":
                        full_response, pending_tool_call, pending_args = await asyncio.wait_for(
                            _run_chat_once([]),
                            timeout=self._voice_planner_timeout_s,
                        )
                    else:
                        full_response, pending_tool_call, pending_args = await _run_chat_once([])
                except asyncio.TimeoutError:
                    logger.warning(
                        "planner_timeout timeout_s=%.2f origin=%s retry_without_tools=true",
                        self._voice_planner_timeout_s,
                        origin,
                    )
                    fallback = "I'm having trouble right now. Please try again."
                    return self._tag_response_with_routing_type(
                        ResponseFormatter.build_response(fallback),
                        "informational",
                    )
                except Exception as retry_err:
                    logger.error(f"❌ Retry without tools also failed: {retry_err}")
                    return self._tag_response_with_routing_type(
                        ResponseFormatter.build_response(fallback_error_text),
                        "informational",
                    )
            else:
                logger.error(f"❌ CHAT stream failed: {e}")
                return self._tag_response_with_routing_type(
                    ResponseFormatter.build_response(fallback_error_text),
                    "informational",
                )

        # If LLM requested a tool call, execute it via the router
        if pending_tool_call:
            import json as _json
            try:
                args = _json.loads(pending_args) if pending_args and pending_args.strip() not in ("", "null") else {}
            except Exception:
                args = {}
            pending_tool_call, args = self._normalize_tool_invocation(pending_tool_call, args)
            tool_output, tool_invocation = await self._execute_tool_call(
                tool_name=pending_tool_call,
                args=args,
                user_id=user_id,
                tool_context=tool_context,
            )
            return await self._synthesize_tool_response(
                role_llm,
                message,
                pending_tool_call,
                tool_output,
                tool_invocation,
                mode="normal",
            )
        else:
            # Some models/providers emit legacy function-tag text instead of
            # structured tool calls; convert it into a real tool execution.
            legacy_call = self._parse_legacy_function_call(full_response)
            if legacy_call:
                tool_name, args = legacy_call
                logger.info(f"🔧 Detected legacy function markup, executing tool: {tool_name}({args})")
                tool_output, tool_invocation = await self._execute_tool_call(
                    tool_name=tool_name,
                    args=args,
                    user_id=user_id,
                    tool_context=tool_context,
                )
                return await self._synthesize_tool_response(
                    role_llm,
                    message,
                    tool_name,
                    tool_output,
                    tool_invocation,
                    mode="normal",
                )
            else:
                full_response = self._sanitize_response(full_response)

        full_response = (full_response or "").strip()
        if self._is_name_query(message) and "maya" not in full_response.lower():
            logger.info("identity_guardrail_applied reason=missing_maya_name")
            full_response = "I'm Maya, your voice assistant."
        if self._is_creator_query(message) and "harsha" not in full_response.lower():
            logger.info("identity_guardrail_applied reason=missing_creator_name")
            full_response = "I'm Maya, and I was created by Harsha."
        if not full_response:
            return self._tag_response_with_routing_type(
                ResponseFormatter.build_response(fallback_error_text),
                "informational",
            )

        if recall_force_toolless:
            response = ResponseFormatter.build_response(
                display_text=full_response,
                voice_text=ResponseFormatter.to_voice_brief(
                    full_response,
                    intent_type="informational",
                ),
            )
            return self._tag_response_with_routing_type(response, "informational")

        response = await self._build_agent_response(role_llm, full_response, mode="normal")
        return self._tag_response_with_routing_type(response, "informational")

