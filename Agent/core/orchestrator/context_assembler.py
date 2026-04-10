"""Context assembly and memory helpers for AgentOrchestrator."""
from __future__ import annotations

import re
import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


class ContextAssembler:
    """Owns context slicing and memory helper plumbing."""

    def __init__(self, *, owner: Any):
        self._owner = owner

    def build_context_slice(
        self,
        *,
        target_agent: str,
        message: str,
        user_id: str,
        tool_context: Any = None,
        host_profile: Dict[str, Any] | None = None,
    ) -> str:
        lines = [f"User request: {str(message or '').strip()}"]
        if self._owner._current_session_id:
            lines.append(f"Session: {self._owner._current_session_id}")
        if getattr(tool_context, "conversation_id", None):
            lines.append(f"Conversation ID: {getattr(tool_context, 'conversation_id')}")
        if self._owner._conversation_history:
            recent = self._owner._conversation_history[-3:]
            summarized = " | ".join(
                f"{item.get('role', 'unknown')}: {str(item.get('content') or '')[:120]}"
                for item in recent
            )
            lines.append(f"Recent context: {summarized}")
        memory_context = ""
        try:
            memory_context = self.retrieve_memory_context(
                str(message or ""),
                user_id=user_id,
                session_id=self._owner._current_session_id,
                origin="chat",
            )
        except Exception as exc:
            logger.debug("context_slice_memory_skipped target=%s error=%s", target_agent, exc)
        if memory_context:
            lines.append(memory_context.strip())
        if target_agent in {"system_operator", "planner"} and host_profile:
            lines.append(self._owner._host_profile_to_text(host_profile))
        return "\n".join([line for line in lines if line]).strip()

    def filter_chat_history_for_fallthrough(self, history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        filtered: List[Dict[str, Any]] = []
        for entry in history:
            if not isinstance(entry, dict):
                filtered.append(entry)
                continue
            role = str(entry.get("role") or "").strip().lower()
            content = str(entry.get("content") or "").strip()
            source = str(entry.get("source") or "").strip().lower()
            if role == "assistant" and source in {"tool_output", "task_step", "direct_action"}:
                continue
            if role == "assistant" and any(
                re.search(pattern, content, flags=re.IGNORECASE)
                for pattern in self._owner.TASK_COMPLETION_PATTERNS
            ):
                continue
            filtered.append(entry)
        return filtered

    def context_message_tokens(self, messages: List[Any]) -> int:
        guard = self._owner.context_guard or self._owner._phase6_context_guard
        if guard is None:
            return sum(len(str(getattr(msg, "content", ""))) // 4 for msg in messages)
        total = 0
        for msg in messages:
            content = getattr(msg, "content", "")
            if isinstance(content, list):
                content_text = " ".join(str(part) for part in content)
            else:
                content_text = str(content)
            total += guard.count_tokens(content_text)
        return total

    @staticmethod
    def chat_ctx_messages(chat_ctx: Any) -> List[Any]:
        messages = getattr(chat_ctx, "messages", [])
        if callable(messages):
            try:
                messages = messages()
            except Exception:
                messages = []
        return list(messages or [])

    @staticmethod
    def message_content_to_text(message: Any) -> str:
        if isinstance(message, dict):
            content = message.get("content")
        else:
            content = getattr(message, "content", None)
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            chunks: List[str] = []
            for part in content:
                if isinstance(part, str):
                    chunks.append(part)
                    continue
                if isinstance(part, dict):
                    text_value = part.get("text") or part.get("content") or ""
                    if text_value:
                        chunks.append(str(text_value))
                    continue
                text_value = getattr(part, "text", None)
                if text_value:
                    chunks.append(str(text_value))
                    continue
                part_content = getattr(part, "content", None)
                if part_content:
                    chunks.append(str(part_content))
            return " ".join(chunk.strip() for chunk in chunks if str(chunk).strip()).strip()
        if isinstance(content, dict):
            return str(content.get("text") or content.get("content") or "").strip()
        if content is None:
            return ""
        return str(content).strip()

    @staticmethod
    def message_role_value(message: Any) -> str:
        if isinstance(message, dict):
            role = message.get("role")
        else:
            role = getattr(message, "role", None)
        return str(role or "").strip().lower()

    def retrieve_memories(
        self,
        user_input: str,
        k: int = 5,
        user_id: str | None = None,
        session_id: str | None = None,
        origin: str = "chat",
    ) -> List[Dict[str, Any]]:
        return self._owner._memory_context_service.retrieve_memories(
            user_input,
            k=k,
            user_id=user_id,
            session_id=session_id,
            origin=origin,
        )

    def format_memory_context(self, memories: List[Dict[str, Any]]) -> str:
        return self._owner._memory_context_service.format_memory_context(memories)

    def retrieve_memory_context(
        self,
        user_input: str,
        k: int = 5,
        user_id: str | None = None,
        session_id: str | None = None,
        origin: str = "chat",
    ) -> str:
        return self._owner._memory_context_service.retrieve_memory_context(
            user_input,
            k=k,
            user_id=user_id,
            session_id=session_id,
            origin=origin,
        )

    async def run_sync_with_timeout(
        self,
        func: Any,
        *args: Any,
        timeout_s: float,
    ) -> Any:
        return await self._owner._memory_context_service.run_sync_with_timeout(
            func,
            *args,
            timeout_s=timeout_s,
        )

    def is_tool_focused_query(self, message: str) -> bool:
        return self._owner._memory_context_service.is_tool_focused_query(message)

    def is_memory_relevant(self, text: str) -> bool:
        return self._owner._memory_context_service.is_memory_relevant(text)

    def is_recall_exclusion_intent(self, text: str) -> bool:
        return self._owner._memory_context_service.is_recall_exclusion_intent(text)

    def should_skip_memory(
        self,
        text: str,
        origin: str,
        routing_mode_type: str,
    ) -> tuple[bool, str]:
        return self._owner._memory_context_service.should_skip_memory(
            text,
            origin,
            routing_mode_type,
        )

    async def retrieve_memory_context_async(
        self,
        user_input: str,
        *,
        origin: str = "chat",
        routing_mode_type: str = "informational",
        user_id: str | None = None,
        session_id: str | None = None,
    ) -> str:
        return await self._owner._memory_context_service.retrieve_memory_context_async(
            user_input,
            origin=origin,
            routing_mode_type=routing_mode_type,
            user_id=user_id,
            session_id=session_id,
        )

    @staticmethod
    def tool_name(tool: Any) -> str:
        name = getattr(tool, "name", None)
        if not name and hasattr(tool, "info"):
            name = getattr(tool.info, "name", None)
        if not name:
            name = getattr(tool, "__name__", "")
        return str(name or "").strip()

    def resolve_phase3_chat_tools(
        self,
        *,
        enable_chat_tools: bool,
        architecture_phase: int,
    ) -> List[Any]:
        if max(1, int(architecture_phase)) < 3:
            return []
        if not enable_chat_tools:
            return []

        allowlist = {
            "open_app",
            "close_app",
            "set_volume",
            "take_screenshot",
            "web_search",
            "get_weather",
            "get_current_datetime",
            "get_date",
            "get_time",
            "set_alarm",
            "list_alarms",
            "delete_alarm",
            "set_reminder",
            "list_reminders",
            "delete_reminder",
            "create_note",
            "list_notes",
            "read_note",
            "delete_note",
            "create_calendar_event",
            "list_calendar_events",
            "delete_calendar_event",
            "send_email",
        }

        try:
            from core.runtime.global_agent import GlobalAgentContainer
            all_tools = GlobalAgentContainer.get_tools() or []
        except Exception as exc:
            logger.warning("⚠️ Failed to resolve global tools for Phase 3: %s", exc)
            return []

        selected: List[Any] = []
        for tool in all_tools:
            name = self.tool_name(tool).lower()
            if name not in allowlist:
                continue
            try:
                if hasattr(tool, "info") and hasattr(tool.info, "parameters"):
                    params = tool.info.parameters
                    if params is None:
                        tool.info.parameters = {"type": "object", "properties": {}, "required": []}
                    elif isinstance(params, dict):
                        params.setdefault("type", "object")
                        params.setdefault("properties", {})
                        params.setdefault("required", [])
                        tool.info.parameters = params
            except Exception as exc:
                logger.warning("⚠️ Tool schema normalization failed for %s: %s", name, exc)
            selected.append(tool)

        logger.info("🧰 Phase 3 tool subset ready: %s tools", len(selected))
        return selected
