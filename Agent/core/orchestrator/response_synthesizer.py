"""Tool-less synthesis and response assembly helpers."""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

from core.response.agent_response import AgentResponse, ToolInvocation
from core.response.response_formatter import ResponseFormatter

logger = logging.getLogger(__name__)


class ResponseSynthesizer:
    """Owns response normalization and tool-less synthesis behavior."""

    def __init__(self, *, owner: Any):
        self._owner = owner

    async def generate_voice_text(self, role_llm: Any, display_text: str) -> str:
        from livekit.agents.llm import ChatContext, ChatMessage

        if not display_text.strip():
            return ""

        system_prompt = (
            "You generate short voice-safe summaries for spoken output. "
            "Rules: 1-2 sentences max. No URLs. No markdown. No lists. "
            "Do not mention sources."
        )
        chat_ctx = ChatContext(
            [
                ChatMessage(role="system", content=[system_prompt]),
                ChatMessage(role="user", content=[display_text]),
            ]
        )
        try:
            logger.info("🧪 synthesis_mode=toolless_explicit target=voice_summary")
            response_text, synthesis_status = await self._owner._run_theless_synthesis_with_timeout(
                chat_ctx,
                role_llm=role_llm,
            )
            self._owner._record_synthesis_metrics(
                synthesis_status=synthesis_status,
                fallback_used=not bool((response_text or "").strip()),
                fallback_source="generic_ack" if not (response_text or "").strip() else "none",
                tool_name="voice_summary",
                mode="voice_summary",
            )
            return response_text.strip()
        except Exception as exc:
            logger.warning("⚠️ Voice summary generation failed: %s", exc)
            return ""

    async def run_theless_synthesis_with_timeout(
        self,
        chat_ctx: Any,
        role_llm: Any = None,
    ) -> tuple[str, str]:
        try:
            text = await asyncio.wait_for(
                self._owner._run_theless_synthesis(chat_ctx, role_llm=role_llm),
                timeout=self._owner._synthesis_timeout_s,
            )
            return text, "ok"
        except asyncio.TimeoutError:
            return "", "timeout"
        except Exception:
            return "", "error"

    async def run_theless_synthesis(self, chat_ctx: Any, role_llm: Any = None) -> str:
        """Execute synthesis with an isolated tool-less model path."""
        stream = None
        response_text = ""
        try:
            base_llm = getattr(getattr(self._owner.agent, "smart_llm", None), "base_llm", None)
            if base_llm is not None:
                logger.info("🧪 synthesis_llm=base_llm_isolated")
                stream = base_llm.chat(
                    chat_ctx=chat_ctx,
                    tools=[],
                    tool_choice="none",
                )
            elif role_llm is not None:
                from core.llm.llm_roles import LLMRole

                logger.info("🧪 synthesis_llm=role_llm_fallback")
                stream = await role_llm.chat(
                    role=LLMRole.CHAT,
                    chat_ctx=chat_ctx,
                    tools=[],
                    tool_choice="none",
                )
            else:
                return ""

            async for chunk in stream:
                delta = ""
                if hasattr(chunk, "choices") and chunk.choices:
                    delta_obj = getattr(chunk.choices[0], "delta", None)
                    if delta_obj:
                        delta = getattr(delta_obj, "content", "") or ""
                elif hasattr(chunk, "delta") and chunk.delta:
                    delta = getattr(chunk.delta, "content", "") or ""
                elif hasattr(chunk, "content"):
                    delta = chunk.content or ""
                if delta:
                    response_text += delta
        finally:
            if stream is not None:
                close_fn = getattr(stream, "aclose", None)
                if callable(close_fn):
                    try:
                        await close_fn()
                    except Exception:
                        pass
        return response_text.strip()

    def record_synthesis_metrics(
        self,
        *,
        synthesis_status: str,
        fallback_used: bool,
        fallback_source: str,
        tool_name: str,
        mode: str,
    ) -> None:
        self._owner._synthesis_total += 1
        if synthesis_status == "timeout":
            self._owner._synthesis_timeout_total += 1
        if fallback_used:
            self._owner._synthesis_fallback_total += 1
        self._owner._synthesis_fallback_window.append(bool(fallback_used))
        fallback_rate = (
            sum(1 for x in self._owner._synthesis_fallback_window if x)
            / float(len(self._owner._synthesis_fallback_window))
            if self._owner._synthesis_fallback_window
            else 0.0
        )
        logger.info(
            "🧪 synthesis_status=%s synthesis_timeout_s=%.2f synthesis_fallback_used=%s "
            "synthesis_fallback_source=%s synthesis_total=%s synthesis_timeout_total=%s "
            "synthesis_fallback_total=%s synthesis_fallback_rate_last_n=%.3f tool_name=%s mode=%s",
            synthesis_status,
            self._owner._synthesis_timeout_s,
            fallback_used,
            fallback_source,
            self._owner._synthesis_total,
            self._owner._synthesis_timeout_total,
            self._owner._synthesis_fallback_total,
            fallback_rate,
            tool_name,
            mode,
        )
        if fallback_rate > self._owner._synthesis_fallback_warn_rate:
            logger.warning(
                "⚠️ SYNTHESIS_FALLBACK_RATE_HIGH rate=%.3f window=%s",
                fallback_rate,
                len(self._owner._synthesis_fallback_window),
            )

    async def build_agent_response(
        self,
        role_llm: Any,
        raw_output: str,
        *,
        mode: str = "normal",
        tool_invocations: Optional[List[ToolInvocation]] = None,
        structured_data: Optional[Dict[str, Any]] = None,
    ) -> AgentResponse:
        sanitized_output = self._owner._sanitize_response(raw_output)
        parsed = ResponseFormatter.parse_agent_response_json(sanitized_output)
        response = ResponseFormatter.normalize_response(
            parsed if parsed else sanitized_output,
            tool_invocations=tool_invocations,
            mode=mode,
            structured_data=structured_data,
        )
        clean_display = self._owner._sanitize_response(response.display_text)
        clean_voice = self._owner._sanitize_response(response.voice_text)
        if clean_display != response.display_text or clean_voice != response.voice_text:
            response = ResponseFormatter.build_response(
                display_text=clean_display or "I completed the action.",
                voice_text=clean_voice or clean_display or "I completed the action.",
                sources=response.sources,
                tool_invocations=response.tool_invocations,
                mode=response.mode,
                memory_updated=response.memory_updated,
                confidence=response.confidence,
                structured_data=response.structured_data,
            )
        if not response.voice_text or response.voice_text.strip() == response.display_text.strip():
            voice_candidate = await self._owner._generate_voice_text(role_llm, response.display_text)
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
        return response
