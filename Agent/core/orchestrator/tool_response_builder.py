"""Tool response normalization and synthesis helpers."""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

from core.response.response_formatter import ResponseFormatter

logger = logging.getLogger(__name__)


class ToolResponseBuilder:
    """Owns tool result normalization and response shaping."""

    def __init__(self, *, owner: Any):
        self._owner = owner

    def classify_tool_intent_type(self, tool_name: str) -> str:
        name = (tool_name or "").strip().lower()
        if name in {
            "get_time",
            "get_date",
            "get_current_datetime",
            "get_weather",
            "web_search",
            "list_alarms",
            "list_reminders",
            "list_notes",
            "list_calendar_events",
            "read_note",
        }:
            return "informational"
        return "direct_action"

    def normalize_tool_result(
        self,
        *,
        tool_name: str,
        raw_result: Any,
        error_code: Optional[str] = None,
    ) -> Dict[str, Any]:
        safe_message = "I was unable to complete that."
        if error_code:
            return {
                "success": False,
                "message": safe_message,
                "error_code": error_code,
                "result": "",
            }

        if isinstance(raw_result, dict):
            if raw_result.get("success") is False:
                message = str(raw_result.get("message") or safe_message).strip() or safe_message
                return {
                    **raw_result,
                    "success": False,
                    "message": message,
                    "error_code": raw_result.get("error_code") or "tool_failed",
                }
            if raw_result.get("error"):
                return {
                    **raw_result,
                    "success": False,
                    "message": safe_message,
                    "error_code": str(raw_result.get("error")),
                }
            return {
                **raw_result,
                "success": True,
                "message": str(raw_result.get("message") or "").strip(),
            }

        text = str(raw_result or "").strip()
        if not text:
            return {"success": True, "message": "", "result": ""}
        if self._owner._TOOL_ERROR_HINT_PATTERN.search(text):
            return {
                "success": False,
                "message": safe_message,
                "error_code": f"{tool_name}_error_text",
                "result": "",
            }
        return {
            "success": True,
            "message": "",
            "result": text,
        }

    def get_tool_response_template(
        self,
        tool_name: str,
        structured_data: Optional[Dict[str, Any]],
        mode: str = "normal",
    ) -> Optional[str]:
        data = structured_data or {}
        name = (tool_name or "").strip().lower()

        if name in {"open_app", "close_app"}:
            app_name = str(data.get("app_name") or data.get("app") or "").strip(" .")
            if app_name:
                verb = "Opened" if name == "open_app" else "Closed"
                return f"{verb} {app_name}."
            return "Done."

        if name == "open_folder":
            folder = str(data.get("folder_name") or data.get("folder_key") or "").strip(" .")
            return f"Opened {folder} folder." if folder else "Opened folder."

        if name == "web_search":
            query = str(data.get("query") or "").strip(" .")
            return f"I found results for {query}." if query else "I found results."

        if name in {"set_alarm", "set_reminder"}:
            return "Reminder set."

        if name == "media_next":
            return "Next track."
        if name == "media_previous":
            return "Previous track."
        if name == "media_play_pause":
            return "Playback toggled."
        if name == "media_stop":
            return "Stopped."

        if name == "get_time":
            value = str(data.get("time") or data.get("result") or "").strip(" .")
            return f"It's {value}." if value else "Here's the current time."

        if name in {"get_date", "get_current_datetime"}:
            value = str(data.get("date") or data.get("result") or "").strip(" .")
            return f"Today is {value}." if value else "Here's today's date."

        if name == "get_weather":
            summary = str(data.get("summary") or "").strip(" .")
            if summary:
                return summary if summary.endswith(".") else f"{summary}."
            condition = str(data.get("condition") or "").strip()
            temp = str(data.get("temp") or data.get("temperature") or "").strip()
            if condition and temp:
                return f"Currently {condition}, {temp}."
            if condition:
                return f"Currently {condition}."
            return "I checked the weather."

        if mode == "direct":
            return "Done."
        return None

    def safe_json_dump(self, data: Any) -> str:
        try:
            return json.dumps(data, ensure_ascii=False)
        except Exception:
            return json.dumps(str(data), ensure_ascii=False)

    async def synthesize_tool_response(
        self,
        role_llm: Any,
        user_message: str,
        tool_name: str,
        tool_output: Any,
        tool_invocation: Any,
        mode: str = "normal",
    ) -> Any:
        from livekit.agents.llm import ChatContext, ChatMessage

        structured_data: Optional[Dict[str, Any]] = None
        if isinstance(tool_output, dict):
            structured_data = tool_output
        elif tool_output is not None:
            structured_data = {"result": str(tool_output)}
        if isinstance(structured_data, dict) and structured_data.get("success") is False:
            safe_text = str(structured_data.get("message") or "I was unable to complete that.").strip()
            response = ResponseFormatter.build_response(
                display_text=safe_text,
                voice_text=safe_text,
                tool_invocations=[tool_invocation],
                mode=mode,
                structured_data=structured_data,
            )
            return self._owner._tag_response_with_routing_type(
                response,
                self.classify_tool_intent_type(tool_name),
            )

        sources = ResponseFormatter.derive_sources(structured_data)
        source_hint = ""
        if sources:
            source_hint = "\nSources:\n" + "\n".join(
                [f"[{idx+1}] {s.title} - {s.url} ({s.snippet or ''})" for idx, s in enumerate(sources)]
            )

        system_prompt = (
            "You are Response Synthesis. Use the tool results to answer the user. "
            "Return ONLY a JSON object with keys: display_text, voice_text, confidence, mode. "
            "display_text must be a single unified answer with inline citations like [1]. "
            "voice_text must be short, URL-free, and markdown-free."
        )
        user_payload = (
            f"User question: {user_message}\n"
            f"Tool used: {tool_name}\n"
            f"Tool output: {self.safe_json_dump(structured_data)}"
            f"{source_hint}"
        )
        chat_ctx = ChatContext(
            [
                ChatMessage(role="system", content=[system_prompt]),
                ChatMessage(role="user", content=[user_payload]),
            ]
        )
        synthesis_fallback_used = False
        synthesis_status = "ok"
        fallback_source = "none"
        try:
            logger.info("🧪 synthesis_mode=toolless_explicit target=tool_response")
            synthesis, synthesis_status = await self._owner._run_theless_synthesis_with_timeout(
                chat_ctx,
                role_llm=role_llm,
            )
        except Exception as e:
            logger.warning(f"⚠️ Tool synthesis failed: {e}")
            synthesis = ""
            synthesis_status = "error"

        if not synthesis.strip():
            display_candidate = ResponseFormatter.extract_display_candidate(structured_data, tool_name)
            if display_candidate:
                synthesis = display_candidate
                fallback_source = "display_candidate"
            else:
                template = self.get_tool_response_template(tool_name, structured_data, mode=mode)
                if template:
                    synthesis = template
                    fallback_source = "tool_template"
                else:
                    synthesis = "I completed the action."
                    fallback_source = "generic_ack"
            synthesis_fallback_used = True

        response = await self._owner._build_agent_response(
            role_llm,
            synthesis,
            mode=mode,
            tool_invocations=[tool_invocation],
            structured_data=structured_data,
        )
        self._owner._record_synthesis_metrics(
            synthesis_status=synthesis_status,
            fallback_used=synthesis_fallback_used,
            fallback_source=fallback_source,
            tool_name=tool_name,
            mode=mode,
        )
        response = self._owner._tag_response_with_routing_type(
            response,
            self.classify_tool_intent_type(tool_name),
        )
        if sources:
            response.sources = sources
        return response

    async def build_direct_tool_response(
        self,
        role_llm: Any,
        tool_output: Any,
        tool_invocation: Any,
    ) -> Any:
        structured_data = tool_output if isinstance(tool_output, dict) else {"result": str(tool_output or "")}
        raw_text = ResponseFormatter.extract_display_candidate(structured_data, tool_invocation.tool_name) or ""
        if not raw_text:
            raw_text = self.get_tool_response_template(
                tool_invocation.tool_name,
                structured_data,
                mode="direct",
            ) or "I completed the action."
        response = await self._owner._build_agent_response(
            role_llm,
            raw_text,
            mode="direct",
            tool_invocations=[tool_invocation],
            structured_data=structured_data,
        )
        return self._owner._tag_response_with_routing_type(
            response,
            self.classify_tool_intent_type(tool_invocation.tool_name),
        )
