"""Session and turn lifecycle helpers for AgentOrchestrator."""
from __future__ import annotations

import logging
import os
import re
import uuid
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class SessionLifecycle:
    """Owns session bootstrap, turn identity, and history lifecycle."""

    def __init__(self, *, owner: Any):
        self._owner = owner

    def set_session_bootstrap_context(self, session_id: str, payload: Dict[str, Any]) -> None:
        session_key = str(session_id or "").strip()
        if not session_key:
            return
        self._owner._session_bootstrap_contexts[session_key] = dict(payload or {})

    def clear_session_bootstrap_context(self, session_id: str) -> None:
        session_key = str(session_id or "").strip()
        if not session_key:
            return
        self._owner._session_bootstrap_contexts.pop(session_key, None)

    def augment_message_with_session_bootstrap(self, message: str, session_id: str) -> str:
        session_key = str(session_id or "").strip()
        payload = self._owner._session_bootstrap_contexts.get(session_key) or {}
        if not payload:
            return message

        topic_summary = str(payload.get("topic_summary") or "").strip()
        recent_events = payload.get("recent_events") or []
        last_tool_results = payload.get("last_tool_results") or []
        conversation_id = str(payload.get("conversation_id") or "").strip()
        project_id = str(payload.get("project_id") or "").strip()
        recent_count = len(recent_events) if isinstance(recent_events, list) else 0
        tool_count = len(last_tool_results) if isinstance(last_tool_results, list) else 0

        logger.info(
            "bootstrap_context_stats session_id=%s conversation_id=%s recent_events_count=%s last_tool_results_count=%s topic_summary_len=%s",
            session_key or "none",
            conversation_id or "none",
            recent_count,
            tool_count,
            len(topic_summary or ""),
        )

        lines: List[str] = []
        if topic_summary:
            lines.append(f"Topic summary: {topic_summary}")
        if conversation_id:
            lines.append(f"Conversation ID: {conversation_id}")
        if project_id:
            lines.append(f"Project ID: {project_id}")
        if isinstance(recent_events, list) and recent_events:
            lines.append("Recent events:")
            for item in recent_events[:6]:
                if not isinstance(item, dict):
                    continue
                role = str(item.get("role") or "").strip() or "system"
                message_type = str(item.get("message_type") or "").strip() or "text"
                content = re.sub(r"\s+", " ", str(item.get("content") or "").strip())
                if not content:
                    continue
                lines.append(f"- {role}/{message_type}: {content}")
        if isinstance(last_tool_results, list) and last_tool_results:
            lines.append("Recent tool results:")
            for item in last_tool_results[:3]:
                if not isinstance(item, dict):
                    continue
                tool_name = str(item.get("tool_name") or "").strip() or "tool"
                summary = re.sub(r"\s+", " ", str(item.get("summary") or "").strip())
                if not summary:
                    continue
                task_id = str(item.get("task_id") or "").strip()
                suffix = f" (task_id={task_id})" if task_id else ""
                lines.append(f"- {tool_name}: {summary}{suffix}")
        if not lines:
            return message

        return (
            "Conversation resume context:\n"
            + "\n".join(lines)
            + "\n\nCurrent user message:\n"
            + str(message or "")
        )

    @staticmethod
    def extract_user_message_segment(augmented: str) -> Optional[str]:
        marker = "\n\nCurrent user message:\n"
        sample = str(augmented or "")
        marker_index = sample.find(marker)
        if marker_index == -1:
            return None
        extracted = sample[marker_index + len(marker):].strip()
        return extracted or None

    def update_turn_identity(self, *, user_id: str, session_id: Optional[str]) -> None:
        self._owner._current_user_id = user_id
        self._owner._current_session_id = session_id

    def start_new_turn(self, user_message: str, turn_id: Optional[str] = None) -> str:
        turn_state = self._owner.turn_state
        turn_state["current_turn_id"] = None
        turn_state["user_message"] = ""
        turn_state["assistant_buffer"] = ""
        turn_state["delta_seq"] = 0
        turn_state["pending_system_action_result"] = ""
        turn_state["pending_tool_result_text"] = ""
        turn_state["pending_task_completion_summary"] = ""

        resolved_turn_id = str(turn_id or uuid.uuid4())
        turn_state["current_turn_id"] = resolved_turn_id
        turn_state["user_message"] = str(user_message or "")

        if hasattr(self._owner.agent, "current_turn_id"):
            self._owner.agent.current_turn_id = resolved_turn_id
        return resolved_turn_id

    def append_conversation_history(
        self,
        role: str,
        content: str,
        source: str = "history",
        route: str = "",
    ) -> None:
        text = str(content or "").strip()
        if not text:
            return
        source_name = str(source or "history")
        self._owner._conversation_history.append(
            {"role": role, "content": text, "source": source_name, "route": str(route or "")}
        )
        max_turns = max(4, int(os.getenv("PHASE6_HISTORY_TURNS", "20")))
        max_messages = max_turns * 2
        if len(self._owner._conversation_history) > max_messages:
            self._owner._conversation_history = self._owner._conversation_history[-max_messages:]

    def inject_session_continuity_summary(self, summary: str) -> bool:
        text = str(summary or "").strip()
        if not text or self._owner._session_continuity_injected:
            return False

        message = f"Context from your last conversation with this user: {text}"
        self.append_conversation_history(
            "assistant",
            message,
            source="session_continuity",
        )
        self._owner._session_continuity_injected = True
        return True

    def resolve_session_queue_key(self, tool_context: Any = None) -> str:
        return (
            getattr(tool_context, "session_id", None)
            or self._owner._current_session_id
            or getattr(getattr(self._owner, "room", None), "name", None)
            or "console_session"
        )

    def set_session(self, session: Any) -> None:
        session_identity = str(id(session))
        if self._owner._attached_session_identity == session_identity:
            logger.info(
                "🟡 ORCHESTRATOR_SESSION_ATTACH_SKIPPED_SAME_SESSION session_identity=%s",
                session_identity,
            )
            return
        logger.info("🔄 Orchestrator switching to new AgentSession: %s", session)
        self._owner.session = session
        self._owner._attached_session_identity = session_identity
        self._owner._session_continuity_injected = False
        self._owner._conversation_history = [
            msg for msg in self._owner._conversation_history
            if str(msg.get("source", "")) != "session_continuity"
        ]
