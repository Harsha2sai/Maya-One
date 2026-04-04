
import logging
import asyncio
import uuid
import json
import re
import inspect
import os
import queue
import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional, List
from core.tasks.planning_engine import PlanningEngine
from core.tasks.task_store import TaskStore
from core.tasks.task_models import Task, TaskStatus
from core.context.context_guard import ContextGuard
from core.telemetry.runtime_metrics import RuntimeMetrics
from core.memory.hybrid_memory_manager import HybridMemoryManager
from core.memory.preference_manager import PreferenceManager
from core.orchestrator.agent_router import AgentRouter
from core.orchestrator.pronoun_rewriter import PronounRewriter
from core.orchestrator.research_handler import ResearchHandler
from core.tools.livekit_tool_adapter import adapt_tool_list
from core.routing.router import get_router
from core.security.input_guard import InputGuard
from core.governance.types import UserRole
from core.utils.intent_utils import normalize_intent
from core.utils.small_talk_detector import is_small_talk
from core.utils.context_signal import get_music_query
from core.agents.contracts import AgentHandoffRequest, HandoffSignal
from core.agents.handoff_manager import get_handoff_manager
from core.agents.registry import get_agent_registry
from livekit import agents
from core.response.response_formatter import ResponseFormatter
from core.response.agent_response import AgentResponse, Source, ToolInvocation
from core.communication import (
    publish_user_message,
    publish_assistant_delta,
    publish_assistant_final,
    publish_agent_thinking,
    publish_tool_execution,
)
from config.settings import settings
from core.observability.trace_context import (
    current_trace_id,
    get_trace_context,
    set_trace_context,
    start_trace,
)

logger = logging.getLogger(__name__)


@dataclass
class DirectToolIntent:
    tool: Optional[str]
    args: Dict[str, Any]
    template: str
    group: str


class _RouterLLMAdapter:
    """Adapter exposing a minimal async .chat(prompt, ...) API for AgentRouter."""

    def __init__(self, agent: Any):
        self._agent = agent

    async def chat(self, prompt: str, max_tokens: int = 10, temperature: float = 0.0) -> str:
        del max_tokens, temperature
        from livekit.agents.llm import ChatContext, ChatMessage

        smart_llm = getattr(self._agent, "smart_llm", None)
        if smart_llm is None:
            raise RuntimeError("smart_llm_unavailable")

        chat_ctx = ChatContext([ChatMessage(role="user", content=[prompt])])
        stream = None
        response_text = ""
        try:
            base_llm = getattr(smart_llm, "base_llm", None)
            if base_llm is not None:
                stream = base_llm.chat(chat_ctx=chat_ctx, tools=[], tool_choice="none")
            else:
                from core.llm.llm_roles import LLMRole
                from core.llm.role_llm import RoleLLM

                role_llm = RoleLLM(smart_llm)
                stream = await role_llm.chat(
                    role=LLMRole.CHAT,
                    chat_ctx=chat_ctx,
                    tools=[],
                    tool_choice="none",
                )

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
                    except Exception as close_err:
                        logger.debug("router_llm_stream_close_failed error=%s", close_err)

        return response_text.strip()


class _NoopMemoryManager:
    def retrieve_relevant_memories(
        self,
        _query: str,
        k: int = 5,
        user_id: str | None = None,
        session_id: str | None = None,
        origin: str = "chat",
    ):
        del k, user_id, session_id, origin
        return []

    async def store_conversation_turn(self, **_kwargs):
        return None


class _NoopIngestor:
    pass


def _coerce_user_role(raw_role: Any, default_role: UserRole = UserRole.USER) -> UserRole:
    """Normalize role values from metadata/context into a concrete UserRole."""
    if isinstance(raw_role, UserRole):
        return raw_role

    if raw_role is None:
        return default_role

    role_key = str(raw_role).strip().upper()
    aliases = {
        "MEMBER": "USER",
        "STANDARD": "USER",
        "POWER": "TRUSTED",
        "POWER_USER": "TRUSTED",
        "SUPERUSER": "ADMIN",
        "OWNER": "ADMIN",
    }
    role_key = aliases.get(role_key, role_key)

    try:
        return UserRole[role_key]
    except Exception:
        logger.warning(f"⚠️ Unknown user role '{raw_role}', defaulting to {default_role.name}")
        return default_role


class AgentOrchestrator:
    """
    Unified Orchestrator that manages both conversational turns and long-running tasks.
    Replaces LegacyOrchestrator inheritance with direct composition.
    """
    def __init__(
        self,
        ctx: Any,
        agent: Any,
        session: Any = None,
        context_guard: Optional[ContextGuard] = None,
        memory_manager: Any = None,
        ingestor: Any = None,
        preference_manager: Any = None,
        enable_chat_tools: bool = False,
        enable_task_pipeline: bool = True,
    ):
        # Legacy fields (previously from LegacyOrchestrator)
        self.ctx = ctx
        self.agent = agent
        self.session = session
        self.room = ctx.room if ctx else None
        self.turn_state = {
            "current_turn_id": None,
            "user_message": "",
            "assistant_buffer": "",
            "delta_seq": 0,
            "last_search_target": "",
            "last_search_query": "",
            "pending_system_action_result": "",
            "pending_tool_result_text": "",
            "pending_task_completion_summary": "",
        }
        self._conversation_history: List[Dict[str, Any]] = []
        self._session_continuity_injected: bool = False
        self._current_user_id: Optional[str] = None
        self._current_session_id: Optional[str] = None
        self._attached_session_identity: Optional[str] = None

        # Planning & task infrastructure
        smart_llm = getattr(agent, "smart_llm", None)
        if not smart_llm:
            logger.warning("AgentOrchestrator: Agent missing smart_llm. Planning might fail.")
        self.planning_engine = PlanningEngine(smart_llm)
        self.task_store = TaskStore()
        self.context_guard = context_guard
        self._phase6_context_guard = context_guard or ContextGuard()

        # Memory and ingestor should be injected in runtime boot paths.
        # We keep no-op fallbacks for tests/dev scripts.
        if not memory_manager:
            logger.warning("⚠️ AgentOrchestrator started without memory_manager; using no-op memory.")
            memory_manager = _NoopMemoryManager()
        if not ingestor:
            logger.warning("⚠️ AgentOrchestrator started without ingestor; using no-op ingestor.")
            ingestor = _NoopIngestor()

        self.memory = memory_manager
        self.ingestor = ingestor
        self.preference_manager = preference_manager
        self._pronoun_rewriter = PronounRewriter()
        if self.preference_manager is None:
            try:
                self.preference_manager = PreferenceManager()
            except Exception as pref_err:
                logger.warning(f"⚠️ Preference manager unavailable; personalization disabled: {pref_err}")
                self.preference_manager = None
        self._memory_timeout_count = 0
        self._memory_disabled_until = 0.0
        self._synthesis_timeout_s = max(
            0.1,
            float(os.getenv("VOICE_SYNTHESIS_TIMEOUT_S", "2.0")),
        )
        self._voice_planner_timeout_s = max(
            0.5,
            float(os.getenv("VOICE_PLANNER_TIMEOUT_S", "8.0")),
        )
        self._synthesis_fallback_window_size = max(
            5,
            int(os.getenv("SYNTHESIS_FALLBACK_WINDOW_SIZE", "50")),
        )
        self._synthesis_fallback_warn_rate = max(
            0.0,
            min(1.0, float(os.getenv("SYNTHESIS_FALLBACK_WARN_RATE", "0.15"))),
        )
        self._synthesis_total = 0
        self._synthesis_timeout_total = 0
        self._synthesis_fallback_total = 0
        self._synthesis_fallback_window = deque(maxlen=self._synthesis_fallback_window_size)
        self._phase6_context_builder_enabled = str(
            os.getenv("PHASE6_CONTEXT_BUILDER_ENABLED", "false")
        ).strip().lower() in {"1", "true", "yes", "on"}
        self._phase6_context_builder_compare_inline = str(
            os.getenv("PHASE6_CONTEXT_BUILDER_COMPARE_INLINE", "false")
        ).strip().lower() in {"1", "true", "yes", "on"}
        self._context_builder: Any = None
        self._research_agent: Any = None
        self._media_agent: Any = None
        self._system_agent: Any = None
        self.enable_chat_tools = enable_chat_tools
        self.enable_task_pipeline = enable_task_pipeline
        self._task_workers: Dict[str, Any] = {}
        self._task_worker_lock = asyncio.Lock()
        self._session_locks: Dict[str, asyncio.Lock] = {}
        self._session_queues: Dict[str, deque] = {}
        self._session_queue_limit = 3
        self._session_bootstrap_contexts: Dict[str, Dict[str, Any]] = {}
        self._last_research_contexts: Dict[str, Dict[str, Any]] = {}
        self._research_context_ttl_s = max(
            10.0,
            float(os.getenv("RESEARCH_CONTEXT_TTL_S", "90")),
        )
        self._research_handler = ResearchHandler(
            context_ttl_s=self._research_context_ttl_s,
            get_conversation_history=lambda: self._conversation_history,
            spawn_background_task=self._spawn_background_task,
        )
        self._enable_research_llm_planner = self._is_truthy_env(
            os.getenv("ENABLE_RESEARCH_LLM_PLANNER", "false")
        )
        self._router = AgentRouter(_RouterLLMAdapter(agent))
        self._agent_registry = get_agent_registry()
        self._handoff_manager = get_handoff_manager(self._agent_registry)
        self._deterministic_tools = {
            "open_app",
            "close_app",
            "open_folder",
            "set_volume",
            "take_screenshot",
            "set_alarm",
            "delete_alarm",
            "set_reminder",
            "delete_reminder",
            "create_note",
            "delete_note",
            "create_calendar_event",
            "delete_calendar_event",
            "get_time",
            "get_date",
            "get_current_datetime",
        }
        self._voice_planner_tools = {
            "get_weather",
            "web_search",
            "set_reminder",
            "take_screenshot",
            "get_current_datetime",
            "run_shell_command",
        }
        self._voice_llm_model = str(
            os.getenv("VOICE_LLM_MODEL", os.getenv("GROQ_MODEL", "llama-3.1-8b-instant"))
        ).strip()
        self._voice_llm_provider = str(
            os.getenv("VOICE_LLM_PROVIDER", os.getenv("LLM_PROVIDER", "groq"))
        ).strip()
        self._voice_planner_llm_override: Any = None
        try:
            from core.context.context_builder import ContextBuilder

            self._context_builder = ContextBuilder(
                llm=getattr(agent, "smart_llm", None),
                memory_manager=self.memory,
                user_id="runtime_user",
                guard=self._phase6_context_guard,
            )
        except Exception as e:
            logger.warning(f"⚠️ Failed to initialize ContextBuilder; inline path only: {e}")
            self._context_builder = None
        logger.info("📁 Using injected MemoryIngestor")
        logger.info(
            "🧪 synthesis_timeout_budget_s=%.2f fallback_window=%s fallback_warn_rate=%.2f planner_timeout_s=%.2f",
            self._synthesis_timeout_s,
            self._synthesis_fallback_window_size,
            self._synthesis_fallback_warn_rate,
            self._voice_planner_timeout_s,
        )
        logger.info(
            "🧩 phase6_context_builder_enabled=%s compare_inline=%s",
            self._phase6_context_builder_enabled,
            self._phase6_context_builder_compare_inline,
        )
        logger.info(
            "🧠 voice_planner_model_override provider=%s model=%s",
            self._voice_llm_provider,
            self._voice_llm_model,
        )

        logger.info("🚀 Enhanced AgentOrchestrator initialized with Planning, TaskStore, and HybridMemory")

    def set_session_bootstrap_context(self, session_id: str, payload: Dict[str, Any]) -> None:
        session_key = str(session_id or "").strip()
        if not session_key:
            return
        self._session_bootstrap_contexts[session_key] = dict(payload or {})

    def clear_session_bootstrap_context(self, session_id: str) -> None:
        session_key = str(session_id or "").strip()
        if not session_key:
            return
        self._session_bootstrap_contexts.pop(session_key, None)

    def _augment_message_with_session_bootstrap(self, message: str, session_id: str) -> str:
        session_key = str(session_id or "").strip()
        payload = self._session_bootstrap_contexts.get(session_key) or {}
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

        bootstrap_note = (
            "Conversation resume context:\n"
            + "\n".join(lines)
            + "\n\nCurrent user message:\n"
            + str(message or "")
        )
        return bootstrap_note

    def _extract_user_message_segment(self, augmented: str) -> Optional[str]:
        """
        Extract raw user message from bootstrap-augmented text.

        Augmented format ends with:
            "\\n\\nCurrent user message:\\n<raw user text>"
        """
        marker = "\n\nCurrent user message:\n"
        sample = str(augmented or "")
        marker_index = sample.find(marker)
        if marker_index == -1:
            return None
        extracted = sample[marker_index + len(marker):].strip()
        return extracted or None

    CONVERSATIONAL_MEMORY_TRIGGERS = (
        r"\b(remember|recall|remind me|earlier|last time|you said|i said|i told you|i asked)\b",
        r"\b(my name|my preference|my usual|what do i|who am i)\b",
        r"\b(what did (i|we|you))\b",
        r"\b(do you know|do you remember)\b",
    )
    RECALL_EXCLUSION_PATTERNS = (
        r"\bwhat\s+did\s+i\s+ask\b",
        r"\bwhat\s+did\s+i\s+say\b",
        r"\bdid\s+i\s+ask\b",
        r"\bdid\s+i\s+say\b",
        r"\bi\s+told\s+you\b",
        r"\byou\s+said\b",
        r"\bwe\s+discussed\b",
    )
    RECALL_EXCLUDED_TOOLS = {"web_search", "get_current_datetime", "get_current_date"}
    TASK_COMPLETION_PATTERNS = (
        r"\bi completed(?: the)? action\b",
        r"\baction cancelled\b",
        r"\btask done\b",
        r"\btask completed\b",
    )
    _TOOL_ERROR_HINT_PATTERN = re.compile(
        r"(traceback|exception|error executing command|timed out|timeout|failed|permission denied|access denied|blocked)",
        flags=re.IGNORECASE,
    )
    _REPORT_EXPORT_PATTERNS = (
        r"\b(save|export)\s+(it|this|that|report|document|file)?\s*(to|in)?\s*(my\s+)?downloads\b",
        r"\b(save|export)\s+(as|into)\s+(docx|document|file)\b",
        r"\b(save|export|write)\s+.*\b(report|document|docx)\b.*\b(downloads|file)\b",
        r"\b(create|generate|prepare)\s+(a\s+)?(report|document|doc)\b.*\b(save|export)\b",
    )
    _REPORT_EXPORT_KEYWORDS = (
        "save to downloads",
        "save it in my downloads",
        "save in my downloads",
        "export report",
        "save as docx",
        "save document",
    )
    _DEEP_RESEARCH_KEYWORDS = (
        "report",
        "in depth",
        "in-depth",
        "detailed",
        "full analysis",
        "thorough",
        "full report",
    )
    MEDIA_PATTERNS = (
        r"\bplay\s+.+",
        r"\bsearch\s+.+\b(song|music|track|playlist|video)\b",
        r"\bqueue\b",
        r"\brecommend\b",
        r"\bsuggest\b.+\bmusic\b",
        r"\bwhat(?:'s| is)\s+playing\b",
        r"\byoutube\b",
        r"\bspotify\b",
    )
    MEDIA_EXCLUDE_PATTERNS = (
        r"\bwhat time is it\b",
        r"^\s*open\s+\w+",
        r"\b(open|close)\s+(firefox|chrome|calculator|folder|downloads)\b",
        r"\b(next|skip|previous|pause|resume|stop music)\b",
    )
    # Pronoun rewriting is handled by PronounRewriter class (P16-02)
    _VOICE_TRANSCRIPTION_NORMALIZATIONS = {
        "diwnloads": "downloads",
        "downlods": "downloads",
        "downlodes": "downloads",
        "donwloads": "downloads",
        "downloades": "downloads",
    }
    _RESEARCH_PRONOUN_TOKENS = {
        "him",
        "her",
        "he",
        "she",
        "it",
        "that",
        "this",
        "they",
        "them",
        "his",
        "their",
    }
    _RESEARCH_SUBJECT_STOPWORDS = {
        "i",
        "you",
        "we",
        "he",
        "she",
        "it",
        "they",
        "him",
        "her",
        "them",
        "this",
        "that",
        "who",
        "what",
        "when",
        "where",
        "why",
        "how",
        "tell",
        "about",
        "me",
        "us",
        "the",
        "a",
        "an",
    }
    _VOICE_SHORT_COMMAND_ALLOWLIST = {
        "yes",
        "no",
        "ok",
        "okay",
        "sure",
        "stop",
        "pause",
        "resume",
        "play",
        "next",
        "continue",
        "cancel",
        "thanks",
        "thank you",
    }
    _VOICE_CONTINUATION_MARKERS = {
        "just",
        "and",
        "but",
        "so",
        "then",
        "also",
        "that",
        "this",
        "it",
    }
    _VOICE_ACTION_SECOND_TOKEN_ALLOWLIST = {
        "open",
        "close",
        "search",
        "play",
        "set",
        "take",
        "run",
        "start",
        "show",
        "list",
    }

    def _classify_tool_intent_type(self, tool_name: str) -> str:
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

    def _tag_response_with_routing_type(
        self,
        response: AgentResponse,
        routing_mode_type: str,
    ) -> AgentResponse:
        mode_type = (routing_mode_type or "informational").strip().lower()
        if mode_type not in {"fast_path", "direct_action", "informational"}:
            mode_type = "informational"
        self.turn_state["routing_mode_type"] = mode_type
        structured = dict(response.structured_data or {})
        structured["_routing_mode_type"] = mode_type
        response.structured_data = structured
        return response

    @staticmethod
    def _is_truthy_env(raw_value: str) -> bool:
        return str(raw_value).strip().lower() in {"1", "true", "yes", "on"}

    def _is_phase6_context_builder_active(self) -> bool:
        return bool(self._phase6_context_builder_enabled and self._context_builder is not None)

    def _resolve_research_agent(self) -> Any:
        if self._research_agent is not None:
            return self._research_agent
        role_llm = None
        try:
            from core.llm.role_llm import RoleLLM

            smart_llm = getattr(self.agent, "smart_llm", None)
            if smart_llm is not None:
                role_llm = RoleLLM(smart_llm)
        except Exception as e:
            logger.warning("research_agent_role_llm_unavailable error=%s", e)

        from core.research.research_agent import ResearchAgent

        self._research_agent = ResearchAgent(role_llm=role_llm)
        logger.warning("research_agent_deprecated_path_used")
        return self._research_agent

    async def _build_research_tasks_inline(self, query: str) -> tuple[list[Any], str]:
        return await self._research_handler.build_research_tasks_inline(
            query,
            enable_llm_planner=self._enable_research_llm_planner,
            smart_llm=getattr(self.agent, "smart_llm", None),
        )

    def _log_research_stage_metrics(
        self,
        *,
        query: str,
        plan_ms: int,
        search_ms: int,
        synth_ms: int,
        source_count: int,
        trace_id: str,
    ) -> None:
        self._research_handler.log_research_stage_metrics(
            query=query,
            plan_ms=plan_ms,
            search_ms=search_ms,
            synth_ms=synth_ms,
            source_count=source_count,
            trace_id=trace_id,
            enable_llm_planner=self._enable_research_llm_planner,
        )

    async def _run_inline_research_pipeline(
        self,
        *,
        query: str,
        user_id: str,
        session_id: str,
        trace_id: str,
    ) -> Any:
        return await self._research_handler.run_inline_research_pipeline(
            query=query,
            user_id=user_id,
            session_id=session_id,
            trace_id=trace_id,
            enable_llm_planner=self._enable_research_llm_planner,
            smart_llm=getattr(self.agent, "smart_llm", None),
            should_use_deep_voice=self._should_use_deep_research_voice(query),
        )

    async def _handle_identity_fast_path(
        self,
        *,
        message: str,
        user_id: str,
        origin: str,
    ) -> AgentResponse:
        import random
        import re

        logger.info("identity_fast_path_matched origin=%s", origin)
        logger.info("context_builder_memory_skipped reason=identity_fast_path")

        WHO_ARE_YOU = (
            "I'm Maya, your AI voice assistant, made by Harsha.",
            "My name is Maya. I'm a voice AI assistant created by Harsha.",
            "I'm Maya — a voice assistant built by Harsha to help you "
            "with research, tasks, system control, and conversation.",
        )

        WHO_MADE_YOU = (
            "I was made by Harsha.",
            "Harsha built me. I'm Maya, a voice AI assistant.",
            "My creator is Harsha. I'm Maya.",
        )

        WHAT_CAN_YOU_DO = (
            "I can help with web research, playing music, opening apps, "
            "managing files, setting reminders, running tasks, and "
            "general conversation. Just ask.",
            "I handle research, system control, media, tasks, and chat. "
            "What do you need?",
        )

        INTRODUCE_YOURSELF = (
            "I'm Maya, a voice AI assistant made by Harsha. I can help "
            "with research, music, apps, files, tasks, and conversation.",
            "Hello — I'm Maya. Harsha built me to be your AI assistant "
            "for voice and chat. How can I help?",
        )

        GENERIC_IDENTITY = (
            "I'm Maya, your AI assistant, made by Harsha.",
        )

        utterance_l = message.lower()

        if re.search(
            r"\bwho\s+(?:made|created|built|developed)\s+you\b"
            r"|\byour\s+(?:creator|developer|maker)\b"
            r"|\bwhat\s+(?:company|team)\s+(?:made|built)\s+you\b",
            utterance_l,
        ):
            responses = WHO_MADE_YOU
        elif re.search(
            r"\bwhat can you do\b|\byour (?:features|capabilities)\b"
            r"|\bhow can you help\b",
            utterance_l,
        ):
            responses = WHAT_CAN_YOU_DO
        elif re.search(r"\bintroduce yourself\b", utterance_l):
            responses = INTRODUCE_YOURSELF
        elif re.search(
            r"\bwho are you\b|\bwhat are you\b"
            r"|\bwhat is your name\b|\byour name\b"
            r"|\bare you an ai\b|\bare you a bot\b",
            utterance_l,
        ):
            responses = WHO_ARE_YOU
        else:
            responses = GENERIC_IDENTITY

        response_text = random.choice(responses)

        return self._tag_response_with_routing_type(
            ResponseFormatter.build_response(
                display_text=response_text,
                voice_text=response_text,
            ),
            "informational",
        )

    def _match_small_talk_fast_path(self, message: str) -> Optional[str]:
        text = str(message or "").strip().lower()
        if not text:
            return None

        if re.search(r"^\s*(hi|hello|hey)\b", text):
            return "Hello. I'm Maya. How can I help you today?"
        if "how are you" in text:
            return "I'm doing well and ready to help. What do you need?"
        if re.search(r"\b(thanks|thank you|cheers)\b", text):
            return "You're welcome."
        if re.search(r"\b(bye|goodbye|see you)\b", text):
            return "Goodbye."
        return None

    def _extract_subject_from_text(self, raw_text: str) -> str:
        text = re.sub(r"\s+", " ", str(raw_text or "")).strip()
        if not text:
            return ""

        capture_patterns = (
            r"\bwho is (?:the )?(.+?)(?:\?|$)",
            r"\btell me about (.+?)(?:\?|$)",
            r"\bwhat about (.+?)(?:\?|$)",
            r"\bi asked you about (.+?)(?:\?|$)",
            r"\b(?:is|was)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})\b",
        )
        for pattern in capture_patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if not match:
                continue
            candidate = re.sub(r"\s+", " ", str(match.group(1) or "")).strip(" .?!,;:")
            if not candidate:
                continue
            tokens = [token.lower() for token in re.findall(r"[A-Za-z']+", candidate)]
            if any(token in self._RESEARCH_PRONOUN_TOKENS for token in tokens):
                continue
            if candidate.lower() in self._RESEARCH_SUBJECT_STOPWORDS:
                continue
            if len(tokens) <= 10:
                return candidate

        named_candidates = re.findall(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3}\b", text)
        for candidate in named_candidates:
            cleaned = candidate.strip()
            if not cleaned:
                continue
            if cleaned.lower() in self._RESEARCH_SUBJECT_STOPWORDS:
                continue
            if len(cleaned.split()) == 1 and len(cleaned) <= 3:
                continue
            return cleaned
        return ""

    def _session_key_for_context(self, tool_context: Any = None) -> str:
        return (
            getattr(tool_context, "session_id", None)
            or self._current_session_id
            or getattr(getattr(self, "room", None), "name", None)
            or "console_session"
        )

    def _extract_summary_sentence(self, summary: str) -> str:
        text = str(summary or "").strip()
        if not text:
            return ""
        text = re.sub(r"(?im)^\s*sources?\s*:.*$", "", text)
        text = re.sub(r"(?im)^\s*[-*•🔹✅🚀]\s*", "", text)
        text = re.sub(r"[*_`#>~]", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        if not text:
            return ""
        sentence = re.split(r"(?<=[.!?])\s+", text, maxsplit=1)[0].strip()
        return sentence.rstrip(" ,;:")

    def _store_research_context(self, query: str, summary: str, *, tool_context: Any = None) -> None:
        session_key = self._session_key_for_context(tool_context)
        self._research_handler.store_research_context(
            query=query,
            summary=summary,
            session_key=session_key,
        )
        active = self._research_handler.get_active_research_context(session_key)
        if active:
            self._last_research_contexts[session_key] = dict(active)

    def _get_active_research_context(self, tool_context: Any = None) -> Optional[Dict[str, Any]]:
        session_key = self._session_key_for_context(tool_context)
        context = self._research_handler.get_active_research_context(session_key)
        if context:
            self._last_research_contexts[session_key] = dict(context)
            return context
        context = self._last_research_contexts.get(session_key)
        if not context:
            return None
        expires_at = float(context.get("expires_at") or 0.0)
        if expires_at <= time.time():
            self._last_research_contexts.pop(session_key, None)
            return None
        return context

    def _resolve_research_subject_from_context(self, tool_context: Any = None) -> str:
        def _is_bad_subject(candidate: str) -> bool:
            if not candidate:
                return True
            lowered = candidate.strip().lower()
            if not lowered:
                return True
            # Avoid filesystem/location nouns from task requests (e.g., "Downloads").
            if lowered in {"downloads", "download", "desktop", "documents", "folder", "file", "pdf"}:
                return True
            if "/" in lowered or "\\" in lowered:
                return True
            return False

        # Source 1: most recent completed research result (session-scoped, TTL guarded)
        context = self._get_active_research_context(tool_context)
        if context:
            candidate = str(context.get("subject") or "").strip()
            if candidate and not _is_bad_subject(candidate):
                return candidate
            candidate = self._extract_subject_from_text(str(context.get("query") or ""))
            if candidate and not _is_bad_subject(candidate):
                return candidate

        history = list(self._conversation_history or [])

        # Source 1: in-session user history (prefer user intent over assistant phrasing)
        for item in reversed(history):
            if str(item.get("source") or "history") != "history":
                continue
            if str(item.get("role") or "").strip().lower() != "user":
                continue
            item_route = str(item.get("route") or "")
            if item_route and item_route != "research":
                continue
            candidate = self._extract_subject_from_text(str(item.get("content") or ""))
            if candidate and not _is_bad_subject(candidate):
                return candidate

        # Source 2: in-session assistant history
        for item in reversed(history):
            if str(item.get("source") or "history") != "history":
                continue
            if str(item.get("role") or "").strip().lower() != "assistant":
                continue
            item_route = str(item.get("route") or "")
            if item_route and item_route != "research":
                continue
            candidate = self._extract_subject_from_text(str(item.get("content") or ""))
            if candidate and not _is_bad_subject(candidate):
                return candidate

        # Source 3: injected continuity summary
        for item in reversed(history):
            if str(item.get("source") or "") != "session_continuity":
                continue
            candidate = self._extract_subject_from_text(str(item.get("content") or ""))
            if candidate and not _is_bad_subject(candidate):
                return candidate

        # Source 4: bootstrap payload
        session_key = (
            getattr(tool_context, "session_id", None)
            or self._current_session_id
            or getattr(getattr(self, "room", None), "name", None)
            or ""
        )
        payload = self._session_bootstrap_contexts.get(str(session_key or "").strip()) or {}
        topic_summary = str(payload.get("topic_summary") or "").strip()
        if topic_summary:
            candidate = self._extract_subject_from_text(topic_summary)
            if candidate and not _is_bad_subject(candidate):
                return candidate

        recent_events = payload.get("recent_events") or []
        if isinstance(recent_events, list):
            for event in reversed(recent_events):
                if not isinstance(event, dict):
                    continue
                candidate = self._extract_subject_from_text(str(event.get("content") or ""))
                if candidate and not _is_bad_subject(candidate):
                    return candidate

        return ""

    def rewrite_research_query_for_context(
        self,
        query: str,
        *,
        tool_context: Any = None,
    ) -> tuple[str, bool, bool]:
        """
        Rewrite a query by resolving pronouns to their antecedent subjects.

        Delegates to PronounRewriter for actual rewriting logic.
        This method provides backward compatibility with existing call sites.

        Args:
            query: The input query potentially containing pronouns
            tool_context: Optional tool context for session resolution

        Returns:
            Tuple of (rewritten_query, changed, ambiguous)
        """
        research_context = self._get_active_research_context(tool_context)
        return self._pronoun_rewriter.rewrite(
            query,
            conversation_history=self._conversation_history,
            research_context=research_context,
            tool_context=tool_context,
        )

    def _rewrite_pronoun_followup_pre_router(
        self,
        raw_query: str,
        *,
        tool_context: Any = None,
    ) -> tuple[str, bool, bool]:
        """
        Pre-router check for pronoun follow-up queries.

        Quick check before routing to determine if pronoun rewriting is needed.
        Delegates to PronounRewriter for actual rewriting.

        Args:
            raw_query: The input query
            tool_context: Optional tool context for session resolution

        Returns:
            Tuple of (rewritten_query, changed, ambiguous)
        """
        query = re.sub(r"\s+", " ", str(raw_query or "")).strip()
        if not query:
            return "", False, False

        # Quick check: skip if no pronouns or followup phrases
        if not self._pronoun_rewriter.should_check_rewrite(query):
            return query, False, False

        # Delegate to main rewrite method
        research_context = self._get_active_research_context(tool_context)
        return self._pronoun_rewriter.rewrite(
            query,
            conversation_history=self._conversation_history,
            research_context=research_context,
            tool_context=tool_context,
        )

    def _normalize_voice_transcription_for_routing(self, message: str) -> tuple[str, bool]:
        text = str(message or "")
        if not text:
            return "", False
        normalized = text
        changed = False
        for garbled, corrected in self._VOICE_TRANSCRIPTION_NORMALIZATIONS.items():
            updated = re.sub(
                rf"\b{re.escape(garbled)}\b",
                corrected,
                normalized,
                flags=re.IGNORECASE,
            )
            if updated != normalized:
                normalized = updated
                changed = True
        return normalized, changed

    async def _handle_research_route(
        self,
        *,
        message: str,
        user_id: str,
        tool_context: Any,
        query_rewritten: bool = False,
        query_ambiguous: bool = False,
    ) -> AgentResponse:
        """Run research in background, return immediate ack to voice."""
        handoff_target = self._consume_handoff_signal(
            target_agent="research",
            execution_mode="inline",
            reason="research_route_selected",
            context_hint=str(message or "")[:160],
        )
        handoff_request = self._build_handoff_request(
            target_agent=handoff_target,
            message=message,
            user_id=user_id,
            execution_mode="inline",
            tool_context=tool_context,
            handoff_reason="research_route_selected",
        )
        handoff_result = await self._handoff_manager.delegate(handoff_request)
        if handoff_result.status == "failed":
            logger.warning(
                "research_handoff_fallback trace_id=%s error_code=%s",
                handoff_request.trace_id,
                handoff_result.error_code,
            )

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
        turn_id = str(uuid.uuid4())
        research_query = (self._extract_user_message_segment(message) or message).strip()
        if not research_query:
            research_query = str(message or "").strip()

        # Resolve room for data channel publish (may be None in console mode)
        room = getattr(tool_context, "room", None)

        active_session = getattr(self, "_session", None) or getattr(self, "session", None)
        background_kwargs = {
            "query": research_query,
            "user_id": user_id,
            "session_id": session_id,
            "trace_id": trace_id,
            "turn_id": turn_id,
            "room": room,
            "session": active_session,
            "task_id": getattr(tool_context, "task_id", None),
            "conversation_id": getattr(tool_context, "conversation_id", None),
        }

        if room is not None:
            await publish_agent_thinking(room, turn_id, "searching")
            await publish_tool_execution(
                room,
                turn_id,
                "web_search",
                "started",
                message="Searching the web for research context.",
                task_id=background_kwargs["task_id"],
                conversation_id=background_kwargs["conversation_id"],
            )

        # In voice/live room mode keep research async. In console mode run inline so
        # the process does not exit before provider chain/synthesis completes.
        if room is not None or active_session is not None:
            self._spawn_background_task(self._run_research_background(**background_kwargs))
        else:
            await self._run_research_background(**background_kwargs)

        self._append_conversation_history(
            "user",
            message,
            source="history",
            route="research",
        )

        # Immediate acknowledgement — routed silently and surfaced via chat events/UI
        logger.info(
            "research_dispatched_to_background",
            extra={
                "trace_id": trace_id,
                "query": research_query,
                "research_query_rewritten": query_rewritten,
                "research_query_ambiguous": query_ambiguous,
            },
        )

        return AgentResponse(
            display_text="",
            voice_text="",
            structured_data={
                "_routing_mode_type": "research_pending",
                "_interaction_mode": "silent_ack",
                "_suppress_assistant_output": True,
                "turn_id": turn_id,
            },
        )

    async def _run_research_background(
        self,
        *,
        query: str,
        user_id: str,
        session_id: str,
        trace_id: str,
        turn_id: str,
        room: Any,
        session: Any,
        task_id: str | None = None,
        conversation_id: str | None = None,
    ) -> None:
        """Background research task. Publishes result to Flutter when done."""
        from core.communication import publish_research_result

        try:
            research_result = await self._run_inline_research_pipeline(
                query=query,
                user_id=user_id,
                session_id=session_id,
                trace_id=trace_id,
            )

            self._research_handler.store_research_context(
                query=query,
                summary=research_result.summary,
                session_key=session_id,
            )
            active = self._research_handler.get_active_research_context(session_id)
            if active:
                self._last_research_contexts[session_id] = dict(active)
            subject = self._research_handler._extract_subject_from_text(query) or "the requested topic"
            summary_sentence = self._research_handler._extract_summary_sentence(research_result.summary)
            history_summary = f"Research result: {subject}. {summary_sentence}".strip()
            self._append_conversation_history(
                "assistant",
                history_summary,
                source="research_summary",
                route="research",
            )

            logger.info(
                "research_background_complete",
                extra={"trace_id": trace_id,
                       "source_count": len(research_result.sources)},
            )

            # Push rich result to Flutter data channel
            if room is not None:
                await publish_tool_execution(
                    room,
                    turn_id,
                    "web_search",
                    "finished",
                    message="Research context is ready.",
                    task_id=task_id,
                    conversation_id=conversation_id,
                )
                await publish_research_result(
                    room,
                    turn_id=turn_id,
                    query=query,
                    summary=research_result.summary,
                    sources=[s.to_dict() for s in research_result.sources],
                    trace_id=trace_id,
                    task_id=task_id,
                    conversation_id=conversation_id,
                )
            else:
                # Console mode — log result for debugging
                logger.info(
                    "research_result_console",
                    extra={"display": research_result.summary[:200] if research_result.summary else "(empty)"}
                )

            sanitized_voice, sanitize_mode = self._sanitize_research_voice_for_tts(
                research_result.voice_summary,
                research_result.summary,
                voice_mode=str(getattr(research_result, "voice_mode", "brief") or "brief"),
            )
            logger.info(
                "research_voice_tts_sanitized mode=%s before_len=%d after_len=%d",
                sanitize_mode,
                len(research_result.voice_summary or ""),
                len(sanitized_voice or ""),
            )

            if sanitized_voice:
                logger.info("tts_voice_summary: %s", (sanitized_voice or "")[:120])
                logger.info(
                    "research_voice_speak turn_id=%s voice_summary_len=%d",
                    turn_id,
                    len(sanitized_voice or ""),
                )

                if session is not None:
                    # Do not speak if a new turn has started since research was dispatched
                    if getattr(self, "_turn_in_progress", False):
                        logger.info(
                            "research_voice_skipped_turn_active turn_id=%s",
                            turn_id,
                        )
                    else:
                        await session.say(
                            sanitized_voice,
                            allow_interruptions=True,
                        )
                else:
                    logger.info("research_voice_skipped reason=no_session turn_id=%s", turn_id)
        except Exception as exc:
            if room is not None:
                await publish_tool_execution(
                    room,
                    turn_id,
                    "web_search",
                    "failed",
                    message="Research request failed before results were ready.",
                    task_id=task_id,
                    conversation_id=conversation_id,
                )
            logger.error(
                "research_background_error",
                extra={"trace_id": trace_id, "error": str(exc)}
            )

    def _is_media_query(self, message: str) -> bool:
        text = str(message or "").strip().lower()
        if not text:
            return False
        for pattern in self.MEDIA_EXCLUDE_PATTERNS:
            if re.search(pattern, text, flags=re.IGNORECASE):
                return False
        return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in self.MEDIA_PATTERNS)

    def _resolve_media_agent(self) -> Any:
        if self._media_agent is not None:
            return self._media_agent
        from core.media.media_agent import MediaAgent

        self._media_agent = MediaAgent()
        return self._media_agent

    def _resolve_system_agent(self) -> Any:
        if self._system_agent is not None:
            return self._system_agent
        from core.system.system_agent import SystemAgent

        self._system_agent = SystemAgent()
        return self._system_agent

    def _get_host_capability_profile(self, refresh: bool = False) -> Optional[Dict[str, Any]]:
        try:
            from core.runtime.global_agent import GlobalAgentContainer

            profile = GlobalAgentContainer.get_host_capability_profile(refresh=refresh)
            if profile is None:
                return None
            if hasattr(profile, "to_dict"):
                payload = profile.to_dict()
            else:
                payload = dict(profile)
            logger.info("host_capability_injected refresh=%s profile=%s", refresh, payload)
            return payload
        except Exception as exc:
            logger.warning("host_capability_unavailable refresh=%s error=%s", refresh, exc)
            return None

    @staticmethod
    def _host_profile_to_text(profile: Optional[Dict[str, Any]]) -> str:
        if not profile:
            return ""
        fields = [
            f"os={profile.get('os')}",
            f"machine={profile.get('machine')}",
            f"cpu_count={profile.get('cpu_count')}",
            f"ram_total_gb={profile.get('ram_total_gb')}",
            f"ram_available_gb={profile.get('ram_available_gb')}",
            f"disk_free_gb={profile.get('disk_free_gb')}",
            f"gpu_present={profile.get('gpu_present')}",
            f"gpu_name={profile.get('gpu_name')}",
            f"runtime_mode={profile.get('runtime_mode')}",
            f"safety_budget={profile.get('safety_budget')}",
        ]
        return "Host Capability Profile: " + ", ".join(fields)

    def _build_context_slice(
        self,
        *,
        target_agent: str,
        message: str,
        user_id: str,
        tool_context: Any = None,
        host_profile: Optional[Dict[str, Any]] = None,
    ) -> str:
        lines = [f"User request: {str(message or '').strip()}"]
        if self._current_session_id:
            lines.append(f"Session: {self._current_session_id}")
        if getattr(tool_context, "conversation_id", None):
            lines.append(f"Conversation ID: {getattr(tool_context, 'conversation_id')}")
        if self._conversation_history:
            recent = self._conversation_history[-3:]
            summarized = " | ".join(
                f"{item.get('role', 'unknown')}: {str(item.get('content') or '')[:120]}"
                for item in recent
            )
            lines.append(f"Recent context: {summarized}")
        memory_context = ""
        try:
            memory_context = self._retrieve_memory_context(
                str(message or ""),
                user_id=user_id,
                session_id=self._current_session_id,
                origin="chat",
            )
        except Exception as exc:
            logger.debug("context_slice_memory_skipped target=%s error=%s", target_agent, exc)
        if memory_context:
            lines.append(memory_context.strip())
        if target_agent in {"system_operator", "planner"} and host_profile:
            lines.append(self._host_profile_to_text(host_profile))
        return "\n".join([line for line in lines if line]).strip()

    def _consume_handoff_signal(
        self,
        *,
        target_agent: str,
        execution_mode: str,
        reason: str,
        context_hint: Optional[str] = None,
    ) -> str:
        signal_name = {
            "research": "transfer_to_research",
            "system_operator": "transfer_to_system_operator",
            "planner": "transfer_to_planner",
            "media": "transfer_to_media",
            "scheduling": "transfer_to_scheduling",
        }[target_agent]
        signal = HandoffSignal(
            signal_name=signal_name,
            reason=reason,
            execution_mode=execution_mode,
            context_hint=context_hint,
        )
        return self._handoff_manager.consume_signal(signal)

    def _build_handoff_request(
        self,
        *,
        target_agent: str,
        message: str,
        user_id: str,
        execution_mode: str,
        intent: Optional[str] = None,
        tool_context: Any = None,
        handoff_reason: str,
        force_task_id: Optional[str] = None,
        host_profile: Optional[Dict[str, Any]] = None,
    ) -> AgentHandoffRequest:
        trace_id = (
            getattr(tool_context, "trace_id", None)
            or current_trace_id()
            or str(uuid.uuid4())
        )
        conversation_id = getattr(tool_context, "conversation_id", None)
        task_id = force_task_id if force_task_id is not None else getattr(tool_context, "task_id", None)
        return AgentHandoffRequest(
            handoff_id=str(uuid.uuid4()),
            trace_id=trace_id,
            conversation_id=conversation_id,
            task_id=task_id,
            parent_agent="maya",
            active_agent="maya",
            target_agent=target_agent,
            intent=str(intent or target_agent),
            user_text=message,
            context_slice=self._build_context_slice(
                target_agent=target_agent,
                message=message,
                user_id=user_id,
                tool_context=tool_context,
                host_profile=host_profile,
            ),
            execution_mode=execution_mode,
            delegation_depth=0,
            max_depth=1,
            handoff_reason=handoff_reason,
            metadata={
                "user_id": user_id,
                "user_role": getattr(getattr(tool_context, "user_role", None), "name", None)
                or getattr(tool_context, "user_role", "USER"),
                "conversation_history": list(self._conversation_history[-5:]),
                "memory_context": "",
                "task_scope": "inline_untracked" if not task_id else "tracked",
                "host_profile": host_profile,
            },
        )

    def _update_turn_identity(
        self,
        *,
        user_id: str,
        session_id: Optional[str],
    ) -> None:
        self._current_user_id = user_id
        self._current_session_id = session_id

    def _start_new_turn(self, user_message: str, turn_id: Optional[str] = None) -> str:
        """
        Reset per-turn transient state before processing a new user turn.
        This prevents completion/result text from leaking across turns.
        """
        # Explicit reset patterns required by safeguards/static analysis.
        self.turn_state["current_turn_id"] = None
        self.turn_state["user_message"] = ""
        self.turn_state["assistant_buffer"] = ""
        self.turn_state["delta_seq"] = 0
        self.turn_state["pending_system_action_result"] = ""
        self.turn_state["pending_tool_result_text"] = ""
        self.turn_state["pending_task_completion_summary"] = ""

        resolved_turn_id = str(turn_id or uuid.uuid4())
        self.turn_state["current_turn_id"] = resolved_turn_id
        self.turn_state["user_message"] = str(user_message or "")

        if hasattr(self.agent, "current_turn_id"):
            self.agent.current_turn_id = resolved_turn_id
        return resolved_turn_id

    def _append_conversation_history(
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
        self._conversation_history.append(
            {"role": role, "content": text, "source": source_name, "route": str(route or "")}
        )
        max_turns = max(4, int(os.getenv("PHASE6_HISTORY_TURNS", "20")))
        max_messages = max_turns * 2
        if len(self._conversation_history) > max_messages:
            self._conversation_history = self._conversation_history[-max_messages:]

    async def _publish_runtime_topic_event(self, topic_name: str, payload: Dict[str, Any]) -> bool:
        room = getattr(self, "room", None)
        if room is None or not hasattr(room, "local_participant"):
            return False
        try:
            raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            await room.local_participant.publish_data(
                raw,
                reliable=True,
                topic=topic_name,
            )
            return True
        except Exception as exc:
            logger.warning("runtime_topic_publish_failed topic=%s error=%s", topic_name, exc)
            return False

    @staticmethod
    def _is_multi_step_task_request(message_lower: str) -> bool:
        text = str(message_lower or "").strip()
        if not text:
            return False
        if any(phrase in text for phrase in ("set a reminder", "set reminder", "reminder to")):
            return True
        sequential_markers = (" and then ", " then open ", " then launch ", " then start ")
        action_markers = (
            "open ",
            "launch ",
            "start ",
            "close ",
            "set ",
            "check ",
            "email ",
            "remind ",
        )
        return any(marker in text for marker in sequential_markers) and any(
            marker in text for marker in action_markers
        )

    def _is_report_export_request(self, message: str) -> bool:
        text = str(message or "").strip().lower()
        if not text:
            return False
        if any(keyword in text for keyword in self._REPORT_EXPORT_KEYWORDS):
            return True
        has_export_verb = bool(
            re.search(r"\b(save|export|download|write|store)\b", text)
        )
        has_file_target = bool(
            re.search(r"\b(downloads|file|docx|document)\b", text)
        )
        has_report_object = bool(re.search(r"\b(report|analysis)\b", text))
        if has_export_verb and (has_file_target or has_report_object):
            return True
        return any(
            re.search(pattern, text, flags=re.IGNORECASE)
            for pattern in self._REPORT_EXPORT_PATTERNS
        )

    def _should_use_deep_research_voice(self, query: str) -> bool:
        text = str(query or "").strip().lower()
        if not text:
            return False
        if any(keyword in text for keyword in self._DEEP_RESEARCH_KEYWORDS):
            return True
        words = re.findall(r"\b[\w'-]+\b", text)
        return len(words) >= 25

    @staticmethod
    def _slugify_topic(text: str) -> str:
        normalized = re.sub(r"[^a-z0-9]+", "-", str(text or "").strip().lower())
        normalized = normalized.strip("-")
        if not normalized:
            return "research-report"
        return normalized[:60]

    def _build_report_output_path(self, query: str) -> str:
        stamp = datetime.now().strftime("%Y%m%d-%H%M")
        topic_slug = self._slugify_topic(query)
        return f"~/Downloads/{topic_slug}-{stamp}.docx"

    @staticmethod
    def _extract_report_focus_query(user_text: str) -> str:
        text = str(user_text or "").strip()
        if not text:
            return ""
        text = re.sub(
            r"(?i)\b(and\s+)?(make|create|write|prepare)\s+(a\s+)?(full\s+)?(report|document|doc)\b",
            " ",
            text,
        )
        text = re.sub(
            r"(?i)\b(and\s+)?(save|export)\s+(it|this|that|report|document)?\s*(to|in)?\s*(my\s+)?downloads\b",
            " ",
            text,
        )
        text = re.sub(r"\s+", " ", text).strip(" ,.")
        return text or str(user_text or "").strip()

    def inject_session_continuity_summary(self, summary: str) -> bool:
        """
        Inject one-time continuity context from the previous session.
        """
        text = str(summary or "").strip()
        if not text or self._session_continuity_injected:
            return False

        message = f"Context from your last conversation with this user: {text}"
        self._append_conversation_history(
            "assistant",
            message,
            source="session_continuity",
        )
        self._session_continuity_injected = True
        return True

    def _filter_chat_history_for_fallthrough(self, history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
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
                for pattern in self.TASK_COMPLETION_PATTERNS
            ):
                continue
            filtered.append(entry)
        return filtered

    def _context_message_tokens(self, messages: List[Any]) -> int:
        guard = self.context_guard or self._phase6_context_guard
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
    def _chat_ctx_messages(chat_ctx: Any) -> List[Any]:
        messages = getattr(chat_ctx, "messages", [])
        if callable(messages):
            try:
                messages = messages()
            except Exception:
                messages = []
        return list(messages or [])

    @staticmethod
    def _message_content_to_text(message: Any) -> str:
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
    def _message_role_value(message: Any) -> str:
        if isinstance(message, dict):
            role = message.get("role")
        else:
            role = getattr(message, "role", None)
        return str(role or "").strip().lower()

    def _is_voice_continuation_fragment(
        self,
        *,
        routing_text: str,
        origin: str,
        chat_ctx_messages: List[Any],
    ) -> bool:
        if str(origin or "").strip().lower() != "voice":
            return False
        if not chat_ctx_messages:
            return False
        normalized = str(routing_text or "").strip().lower()
        if not normalized:
            return False
        if normalized in self._VOICE_SHORT_COMMAND_ALLOWLIST:
            return False

        tokens = re.findall(r"\b[\w'-]+\b", normalized)
        if not tokens or len(tokens) > 6:
            return False
        if len(tokens) == 1 and tokens[0] in self._VOICE_SHORT_COMMAND_ALLOWLIST:
            return False
        if tokens[0] not in self._VOICE_CONTINUATION_MARKERS:
            return False
        if len(tokens) > 1 and tokens[1] in self._VOICE_ACTION_SECOND_TOKEN_ALLOWLIST:
            return False

        # Require at least one prior assistant turn so we only gate true follow-up fragments.
        for message in reversed(chat_ctx_messages):
            if self._message_role_value(message) != "assistant":
                continue
            if self._message_content_to_text(message):
                return True
        return False

    def _tool_name(self, tool: Any) -> str:
        """Best-effort tool name extraction across wrapped tool types."""
        name = getattr(tool, "name", None)
        if not name and hasattr(tool, "info"):
            name = getattr(tool.info, "name", None)
        if not name:
            name = getattr(tool, "__name__", "")
        return str(name or "").strip()

    async def _maybe_await(self, value: Any) -> Any:
        if inspect.isawaitable(value):
            return await value
        return value

    def _resolve_phase3_chat_tools(self) -> List[Any]:
        """
        Returns a safe, schema-normalized tool subset for Phase 3 chat routing.
        Keeps destructive/local-shell tools out of the first tool-enabled phase.
        """
        if max(1, int(getattr(settings, "architecture_phase", 1))) < 3:
            return []
        if not self.enable_chat_tools:
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
        except Exception as e:
            logger.warning(f"⚠️ Failed to resolve global tools for Phase 3: {e}")
            return []

        selected = []
        for tool in all_tools:
            name = self._tool_name(tool).lower()
            if name not in allowlist:
                continue

            # Strict schema guard for providers that reject missing properties.
            try:
                if hasattr(tool, "info") and hasattr(tool.info, "parameters"):
                    params = tool.info.parameters
                    if params is None:
                        tool.info.parameters = {
                            "type": "object",
                            "properties": {},
                            "required": [],
                        }
                    elif isinstance(params, dict):
                        params.setdefault("type", "object")
                        params.setdefault("properties", {})
                        params.setdefault("required", [])
                        tool.info.parameters = params
            except Exception as e:
                logger.warning(f"⚠️ Tool schema normalization failed for {name}: {e}")

            selected.append(tool)

        logger.info(f"🧰 Phase 3 tool subset ready: {len(selected)} tools")
        return selected

    def _parse_legacy_function_call(self, text: str) -> Optional[tuple[str, Dict[str, Any]]]:
        """
        Parse model-emitted legacy function markup like:
        <function>web_search{"query":"..."}</function>
        """
        if not text:
            return None

        match = re.search(
            r"<function>\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*(\{.*?\})?\s*</function>",
            text,
            re.IGNORECASE | re.DOTALL,
        )
        if not match:
            # Also support plain malformed variants such as:
            # web_search={"query":"..."}  OR  web_search{"query":"..."}
            flat_match = re.search(
                r"^\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*(?:=)?\s*(\{.*\})\s*$",
                text.strip(),
                re.IGNORECASE | re.DOTALL,
            )
            if not flat_match:
                return None
            match = flat_match

        tool_name = (match.group(1) or "").strip()
        args_blob = (match.group(2) or "").strip()
        args: Dict[str, Any] = {}
        if args_blob:
            try:
                parsed = json.loads(args_blob)
                if isinstance(parsed, dict):
                    args = parsed
            except Exception:
                # Lightweight fallback for common malformed payloads.
                query_match = re.search(r'"query"\s*:\s*"([^"]+)"', args_blob)
                if query_match:
                    args = {"query": query_match.group(1)}

        if not tool_name:
            return None
        return (tool_name, args)

    def _is_tool_call_generation_error(self, err: Exception) -> bool:
        """
        Detect provider-side function-call formatting failures that should
        trigger a no-tools retry instead of failing the turn.
        """
        msg = str(err or "").lower()
        patterns = (
            "failed to call a function",
            "tool call validation failed",
            "attempted to call tool",
            "not in request.tools",
            "invalid tool",
            "invalid function call",
        )
        return any(p in msg for p in patterns)

    def _normalize_tool_invocation(
        self,
        tool_name: str,
        args: Dict[str, Any],
    ) -> tuple[str, Dict[str, Any]]:
        """
        Repair malformed tool names occasionally emitted by providers, e.g.
        `web_search={\"query\":\"x\"}` or `web_search{\"query\":\"x\"}`.
        """
        normalized_name = str(tool_name or "").strip()
        normalized_args: Dict[str, Any] = dict(args or {})

        def _merge_json_blob(blob: str) -> None:
            blob = (blob or "").strip()
            if not blob:
                return
            if not blob.startswith("{"):
                return
            try:
                parsed = json.loads(blob)
                if isinstance(parsed, dict):
                    normalized_args.update(parsed)
                    return
            except Exception:
                pass

            query_match = re.search(r'"query"\s*:\s*"([^"]+)"', blob)
            if query_match:
                normalized_args.setdefault("query", query_match.group(1))

        # Pattern: tool_name={...}
        if "=" in normalized_name:
            left, right = normalized_name.split("=", 1)
            if left.strip():
                normalized_name = left.strip()
                _merge_json_blob(right)

        # Pattern: tool_name{...}
        brace_idx = normalized_name.find("{")
        if brace_idx > 0 and normalized_name.endswith("}"):
            embedded_blob = normalized_name[brace_idx:]
            normalized_name = normalized_name[:brace_idx].strip()
            _merge_json_blob(embedded_blob)

        return normalized_name, normalized_args

    def _strip_legacy_function_markup(self, text: str) -> str:
        if not text:
            return ""
        cleaned = re.sub(
            r"<function>\s*[a-zA-Z_][a-zA-Z0-9_]*\s*(?:\{.*?\})?\s*</function>",
            "",
            text,
            flags=re.IGNORECASE | re.DOTALL,
        )
        return cleaned.strip()

    def _sanitize_response(self, text: str) -> str:
        """
        Remove leaked tool-markup payloads before any UI/TTS publish path.
        Handles both closed and unclosed variants:
        - <tool_name>{...}</tool_name>
        - <tool_name>{...}
        """
        if not text:
            return ""

        cleaned = self._strip_legacy_function_markup(text)
        leak_detected = False

        closed_tag_pattern = re.compile(
            r"<([a-zA-Z_][\w-]*)>\s*\{[\s\S]*?\}\s*</\1>",
            flags=re.IGNORECASE,
        )
        open_tag_pattern = re.compile(
            r"<([a-zA-Z_][\w-]*)>\s*\{[\s\S]*?\}(?:\s|$)",
            flags=re.IGNORECASE,
        )

        if closed_tag_pattern.search(cleaned):
            leak_detected = True
            cleaned = closed_tag_pattern.sub(" ", cleaned)

        if open_tag_pattern.search(cleaned):
            leak_detected = True
            cleaned = open_tag_pattern.sub(" ", cleaned)

        if leak_detected:
            logger.warning("tool_markup_leak_detected")

        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned

    def _sanitize_research_voice_for_tts(
        self,
        voice: str,
        display: str,
        *,
        voice_mode: str = "brief",
    ) -> tuple[str, str]:
        """Return clean TTS text for research results."""
        from core.research.result_synthesizer import ResultSynthesizer

        def _has_json_signatures(text: str) -> bool:
            sample = str(text or "")
            return bool(
                re.search(r'(?i)"?\b(display|voice)\b"?\s*:', sample)
                or re.search(r"[{}]", sample)
            )

        raw_voice = str(voice or "").strip()
        if not raw_voice:
            display_fallback = ResultSynthesizer._normalize_voice(
                ResultSynthesizer._voice_from_display(display, voice_mode=voice_mode),
                voice_mode=voice_mode,
            )
            if display_fallback:
                return display_fallback, "display_fallback"
            return "", "empty"

        direct = ResultSynthesizer._normalize_voice(
            self._sanitize_response(raw_voice),
            voice_mode=voice_mode,
        )
        if direct and not _has_json_signatures(direct):
            return direct, "direct"

        cleaned_source = re.sub(r'(?i)"?\b(display|voice)\b"?\s*:\s*', " ", raw_voice)
        cleaned_source = re.sub(r"[{}\"]", " ", cleaned_source)
        cleaned_source = re.sub(r"(?im)^\s*sources?\s*:.*$", " ", cleaned_source)
        cleaned_source = re.sub(r"\s+", " ", cleaned_source).strip()
        cleaned = ResultSynthesizer._normalize_voice(
            self._sanitize_response(cleaned_source),
            voice_mode=voice_mode,
        )
        if cleaned and not _has_json_signatures(cleaned):
            return cleaned, "cleaned"

        display_fallback = ResultSynthesizer._normalize_voice(
            ResultSynthesizer._voice_from_display(display, voice_mode=voice_mode),
            voice_mode=voice_mode,
        )
        if display_fallback and not _has_json_signatures(display_fallback):
            return display_fallback, "display_fallback"
        return "", "empty"

    def _parse_multi_app(self, app_phrase: str) -> List[str]:
        """
        Parse "open X and Y" / "open X, Y" into one shell command per app.
        Returns empty list when phrase is not multi-app or not safely mappable.
        """
        phrase = (app_phrase or "").strip().lower().strip(" .,!?:;")
        if not phrase:
            return []

        parts = [p.strip() for p in re.split(r"\s*(?:,|&|\band\b)\s*", phrase) if p.strip()]
        if len(parts) < 2:
            return []

        command_map = {
            "firefox": "firefox",
            "chrome": "google-chrome",
            "google chrome": "google-chrome",
            "chromium": "chromium-browser",
            "brave": "brave-browser",
            "edge": "microsoft-edge",
            "calculator": "gnome-calculator",
            "files": "nautilus",
            "file manager": "nautilus",
            "terminal": "gnome-terminal",
        }

        commands: List[str] = []
        for raw_part in parts:
            part = re.sub(r"^\b(the|my)\b\s+", "", raw_part).strip()
            part = re.sub(r"\s+\b(app|application)\b$", "", part).strip()
            cmd = command_map.get(part)
            if not cmd:
                return []
            commands.append(cmd)

        # Preserve order while de-duplicating.
        deduped = list(dict.fromkeys(commands))
        return deduped if len(deduped) > 1 else []

    # ─── Inlined from legacy.py ────────────────────────────────────────────────

    def set_session(self, session: Any):
        """Update the active LiveKit session (used for audio recovery)."""
        session_identity = str(id(session))
        if self._attached_session_identity == session_identity:
            logger.info(
                "🟡 ORCHESTRATOR_SESSION_ATTACH_SKIPPED_SAME_SESSION session_identity=%s",
                session_identity,
            )
            return
        logger.info(f"🔄 Orchestrator switching to new AgentSession: {session}")
        self.session = session
        self._attached_session_identity = session_identity
        self._session_continuity_injected = False
        self._conversation_history = [
            msg for msg in self._conversation_history
            if str(msg.get("source", "")) != "session_continuity"
        ]

    def setup_handlers(self):
        """Registers all event handlers for the room and session. Idempotent — safe to call multiple times."""
        if getattr(self, '_handlers_registered', False):
            logger.warning("⚠️ setup_handlers() called more than once on same orchestrator — skipping duplicate registration.")
            return
        if self.room:
            self.room.on("transcription_received", self._on_transcription_received)
            self.room.on("data_received", self._on_data_received)
            self._handlers_registered = True
            logger.info("📡 Event handlers successfully registered")

    @staticmethod
    def _log_background_task_exception(task: asyncio.Task) -> None:
        if task.cancelled():
            return
        try:
            error = task.exception()
        except Exception as e:
            logger.error("unhandled_task_exception", extra={"error": str(e)})
            return
        if error:
            logger.error("unhandled_task_exception", extra={"error": str(error)})

    def _spawn_background_task(self, coro: Any) -> asyncio.Task:
        task = asyncio.create_task(coro)
        if not isinstance(task, asyncio.Task):
            if inspect.iscoroutine(coro):
                coro.close()
            return task
        task.add_done_callback(self._log_background_task_exception)
        return task

    async def _handle_task_worker_event(self, event: Dict[str, Any]) -> None:
        event_type = str((event or {}).get("event_type") or "").strip() or "unknown"
        message = str((event or {}).get("voice_text") or (event or {}).get("message") or "").strip()
        logger.info(
            "task_event_received event_type=%s task_id=%s trace_id=%s",
            event_type,
            (event or {}).get("task_id"),
            (event or {}).get("trace_id"),
        )
        if not message:
            return
        if self.session:
            self._spawn_background_task(self._announce(message))

    def _on_transcription_received(self, transcription):
        """Handle user transcription events and publish to data channel."""
        try:
            if transcription.is_final and transcription.participant and transcription.participant.is_local:
                turn_id = self._start_new_turn(transcription.text)

                self._spawn_background_task(
                    publish_user_message(self.room, turn_id, transcription.text)
                )
                self._spawn_background_task(
                    publish_agent_thinking(self.room, turn_id, "thinking")
                )
        except Exception as e:
            logger.error(f"❌ Error handling transcription: {e}")

    async def process_chat_message(self, text: str):
        """Processes text-based chat messages by updating context and triggering reply."""
        try:
            logger.info(f"📝 Adding user text to agent context: {text}")
            if hasattr(self.agent, "chat_ctx") and hasattr(self.agent, "update_chat_ctx"):
                new_ctx = self.agent.chat_ctx.copy()
                new_ctx.add_message(role="user", content=text)
                await self.agent.update_chat_ctx(new_ctx)
                logger.info("✅ Chat context updated")
            logger.info("🤖 Triggering agent reply...")
            self.session.generate_reply()
        except Exception as e:
            logger.error(f"❌ Error in process_chat_message: {e}")

    def _on_data_received(self, *args):
        """Handles incoming data messages (e.g., from the chat UI)."""
        try:
            data, topic = None, None
            if len(args) >= 4:
                data, topic = args[0], args[3]
            elif len(args) == 1:
                obj = args[0]
                data = getattr(obj, "data", None)
                topic = getattr(obj, "topic", None)
            if (topic == "chat" or topic == "lk.chat") and data:
                text = data.decode("utf-8")
                logger.info(f"📩 Chat message received: {text}")
                self._spawn_background_task(self.process_chat_message(text))
        except Exception as e:
            logger.error(f"❌ Error handling data message: {e}")

    @staticmethod
    def parse_client_config(participant: Any) -> Dict[str, Any]:
        """Parses client configuration from participant metadata."""
        if not participant.metadata:
            return {}
        try:
            config = json.loads(participant.metadata)
            logger.info(f"🔧 Parsed client config: {config}")
            return config
        except Exception as e:
            logger.warning(f"⚠️ Failed to parse metadata: {e}")
            return {}

    # ─── End inlined legacy methods ────────────────────────────────────────────

    def _retrieve_memories(
        self,
        user_input: str,
        k: int = 5,
        user_id: str | None = None,
        session_id: str | None = None,
        origin: str = "chat",
    ) -> List[Dict[str, Any]]:
        """
        Retrieve relevant long-term memories.
        Skips memory retrieval for small talk messages to reduce latency and tokens.
        """
        if is_small_talk(user_input):
            logger.debug(f"Small talk detected, skipping memory retrieval for: {user_input[:30]}...")
            return []

        try:
            memories = self.memory.retrieve_relevant_memories(
                user_input,
                k=k,
                user_id=user_id,
                session_id=session_id,
                origin=origin,
            )
            if not memories:
                return []
            RuntimeMetrics.increment("memory_hits_total")
            return memories
        except Exception as e:
            logger.error(f"Error retrieving memory context: {e}")
            return []

    def _format_memory_context(self, memories: List[Dict[str, Any]]) -> str:
        if not memories:
            return ""
        formatted = "\n".join([f"- {m['text']}" for m in memories if isinstance(m, dict) and m.get("text")])
        if not formatted:
            return ""
        return f"\nRelevant past memories:\n{formatted}\n"

    def _retrieve_memory_context(
        self,
        user_input: str,
        k: int = 5,
        user_id: str | None = None,
        session_id: str | None = None,
        origin: str = "chat",
    ) -> str:
        memories = self._retrieve_memories(
            user_input,
            k=k,
            user_id=user_id,
            session_id=session_id,
            origin=origin,
        )
        return self._format_memory_context(memories)

    async def _run_sync_with_timeout(
        self,
        func: Any,
        *args: Any,
        timeout_s: float,
    ) -> Any:
        """Run a blocking fallback in a daemon thread without tying up the loop executor."""
        loop = asyncio.get_running_loop()
        result_queue: "queue.Queue[tuple[bool, Any]]" = queue.Queue(maxsize=1)

        def _runner() -> None:
            try:
                result_queue.put((True, func(*args)))
            except BaseException as exc:  # pragma: no cover - defensive wrapper
                result_queue.put((False, exc))

        threading.Thread(target=_runner, daemon=True).start()

        deadline = loop.time() + timeout_s
        while True:
            try:
                ok, payload = result_queue.get_nowait()
            except queue.Empty:
                if loop.time() >= deadline:
                    raise asyncio.TimeoutError()
                await asyncio.sleep(0.01)
                continue

            if ok:
                return payload
            raise payload

    def _is_tool_focused_query(self, message: str) -> bool:
        """Fast heuristic to skip expensive retrieval for obvious tool-style queries."""
        text = (message or "").lower()
        keywords = (
            "time", "date", "today", "weather", "alarm", "reminder", "note", "calendar",
            "email", "search", "find", "tool", "use ", "what is", "what's", "tell me",
        )
        return any(k in text for k in keywords)

    def _is_memory_relevant(self, text: str) -> bool:
        sample = (text or "").lower()
        return any(re.search(pattern, sample) for pattern in self.CONVERSATIONAL_MEMORY_TRIGGERS)

    def _is_recall_exclusion_intent(self, text: str) -> bool:
        sample = (text or "").lower()
        return any(re.search(pattern, sample) for pattern in self.RECALL_EXCLUSION_PATTERNS)

    def _should_skip_memory(
        self,
        text: str,
        origin: str,
        routing_mode_type: str,
    ) -> tuple[bool, str]:
        if self._is_name_query(text) or self._is_creator_query(text):
            return True, "capability_or_identity_query"

        if re.search(
            r"\b(introduce yourself|tell me about yourself|what can you do|what are your capabilities|are you an ai|are you a bot|what is maya|what are your features)\b",
            (text or "").lower(),
        ):
            return True, "capability_or_identity_query"

        if origin != "voice":
            return False, "not_voice"

        if routing_mode_type in ("fast_path", "direct_action"):
            return True, routing_mode_type

        if self._is_memory_relevant(text):
            return False, "conversational"

        return True, "no_recall_trigger"

    async def _retrieve_memory_context_async(
        self,
        user_input: str,
        *,
        origin: str = "chat",
        routing_mode_type: str = "informational",
        user_id: str | None = None,
        session_id: str | None = None,
    ) -> str:
        """
        Retrieve memory without blocking the event loop.
        Time-box retrieval to prevent worker unresponsive kills on heavy first-load paths.
        """
        if str(os.getenv("MAYA_DISABLE_MEMORY_RETRIEVAL", "false")).strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }:
            logger.info(
                "🧠 memory_skipped=true memory_skip_reason=disabled origin=%s routing_mode_type=%s",
                origin,
                routing_mode_type,
            )
            return ""

        skip_memory, skip_reason = self._should_skip_memory(user_input, origin, routing_mode_type)
        if skip_memory:
            logger.info(
                "🧠 memory_skipped=true memory_skip_reason=%s origin=%s routing_mode_type=%s",
                skip_reason,
                origin,
                routing_mode_type,
            )
            return ""

        if origin != "voice" and self._is_tool_focused_query(user_input):
            logger.info(
                "🧠 memory_skipped=true memory_skip_reason=tool_focused_chat origin=%s routing_mode_type=%s",
                origin,
                routing_mode_type,
            )
            return ""

        loop = asyncio.get_running_loop()
        if loop.time() < self._memory_disabled_until:
            logger.info(
                "🧠 memory_skipped=true memory_skip_reason=temporary_disable origin=%s routing_mode_type=%s",
                origin,
                routing_mode_type,
            )
            return ""

        voice_memory_max_results = max(1, int(os.getenv("VOICE_MEMORY_MAX_RESULTS", "2")))
        max_results = voice_memory_max_results if origin == "voice" else 5
        fallback_timeout_s = max(0.1, float(os.getenv("VOICE_MEMORY_TIMEOUT_S", "0.60"))) if origin == "voice" else 2.0
        started = loop.time()

        try:
            if hasattr(self.memory, "retrieve_relevant_memories_with_scope_fallback_async"):
                memories = await self.memory.retrieve_relevant_memories_with_scope_fallback_async(
                    user_input,
                    k=max_results,
                    user_id=user_id,
                    session_id=session_id,
                    origin=origin,
                )
            elif hasattr(self.memory, "retrieve_relevant_memories_async"):
                memories = await self.memory.retrieve_relevant_memories_async(
                    user_input,
                    k=max_results,
                    user_id=user_id,
                    session_id=session_id,
                    origin=origin,
                )
            else:
                try:
                    memories = await self._run_sync_with_timeout(
                        self._retrieve_memories,
                        user_input,
                        max_results,
                        user_id,
                        session_id,
                        origin,
                        timeout_s=fallback_timeout_s,
                    )
                except TypeError:
                    # Backward compatibility for tests/stubs monkeypatching legacy signature.
                    memories = await self._run_sync_with_timeout(
                        self._retrieve_memories,
                        user_input,
                        max_results,
                        timeout_s=fallback_timeout_s,
                    )
            memory_context = self._format_memory_context(memories)
            elapsed_ms = max(0.0, (loop.time() - started) * 1000.0)
            self._memory_timeout_count = 0
            logger.info(
                "🧠 memory_skipped=false memory_skip_reason=%s memory_budget_s=%s memory_ms=%.2f memory_results_count=%s origin=%s routing_mode_type=%s",
                skip_reason,
                "managed_by_retriever",
                elapsed_ms,
                len(memories),
                origin,
                routing_mode_type,
            )
            return memory_context
        except Exception as e:
            logger.warning(f"⚠️ Async memory retrieval failed: {e}")
            return ""

    def _is_malformed_short_request(self, message: str) -> bool:
        """
        Catch clearly malformed short inputs and request a clean rephrase.
        Keeps recovery behavior deterministic across direct and Flutter paths.
        """
        text = (message or "").strip().lower()
        if not text:
            return True

        words = re.findall(r"[a-z]{2,}", text)
        weird_tokens = len(re.findall(r"[\[\]\{\}]", text))
        punctuation = len(re.findall(r"[^\w\s]", text))

        if weird_tokens > 0 and len(words) <= 4:
            return True
        if len(text) <= 32 and punctuation >= 4 and len(words) <= 3:
            return True
        return False

    def _is_conversational_query(self, message: str) -> bool:
        text = (message or "").strip().lower()
        if not text:
            return False
        patterns = (
            r"\b(what(?:'s| is)\s+your\s+name|who\s+are\s+you|who\s+(?:made|created|built)\s+you|what\s+are\s+you)\b",
            r"\b(what can you do|how can you help)\b",
            r"\b(thanks|thank you|cheers)\b",
            r"\b(hi|hello|hey|good morning|good evening)\b",
            r"\b(bye|goodbye|see you)\b",
        )
        return any(re.search(p, text) for p in patterns)

    def _is_name_query(self, message: str) -> bool:
        text = (message or "").strip().lower()
        if not text:
            return False
        return bool(re.search(r"\b(what(?:'s| is)\s+your\s+name|who\s+are\s+you)\b", text))

    def _is_creator_query(self, message: str) -> bool:
        text = (message or "").strip().lower()
        if not text:
            return False
        return bool(re.search(r"\b(who\s+(?:made|created|built)\s+you|who\s+is\s+your\s+creator)\b", text))

    def _is_user_name_recall_query(self, message: str) -> bool:
        text = (message or "").strip().lower()
        if not text:
            return False
        return bool(
            re.search(
                r"\b(what(?:'s| is)\s+my\s+name|do you know my name|what do you know about me|what have i told you about me)\b",
                text,
            )
        )

    @staticmethod
    def _extract_name_from_memory_messages(messages: List[Any]) -> Optional[str]:
        name_pattern = re.compile(r"\bmy name is\s+([A-Za-z][A-Za-z0-9' -]{0,40})", re.IGNORECASE)
        profile_pattern = re.compile(
            r"\buser profile fact:\s*name\s*=\s*([A-Za-z][A-Za-z0-9' -]{0,40})",
            re.IGNORECASE,
        )
        for message in messages or []:
            source = ""
            content: Any = ""
            if isinstance(message, dict):
                source = str(message.get("source", "")).lower()
                content = message.get("content", "")
            else:
                source = str(getattr(message, "source", "")).lower()
                content = getattr(message, "content", "")
            if source != "memory" and "[memory" not in str(content).lower():
                continue
            content_text = content if isinstance(content, str) else str(content)
            match = name_pattern.search(content_text) or profile_pattern.search(content_text)
            if match:
                return match.group(1).strip().strip(".,!?;:\"'")
        return None

    async def _lookup_profile_name_from_memory(
        self,
        *,
        user_id: str,
        session_id: str | None,
        origin: str = "chat",
    ) -> Optional[str]:
        """
        Fallback lookup for canonical profile facts when semantic memory snippets
        do not include an explicit "my name is ..." line.
        """
        try:
            retriever = getattr(self.memory, "retrieve_relevant_memories_with_scope_fallback_async", None)
            if not callable(retriever):
                return None
            memories = await retriever(
                query="User profile fact: name=",
                user_id=user_id,
                session_id=session_id,
                origin=origin,
                k=6,
            )
        except Exception as e:
            logger.warning("profile_name_lookup_failed user_id=%s session_id=%s error=%s", user_id, session_id, e)
            return None

        profile_pattern = re.compile(
            r"\buser profile fact:\s*name\s*=\s*([A-Za-z][A-Za-z0-9' -]{0,40})",
            re.IGNORECASE,
        )
        for item in memories or []:
            meta = item.get("metadata") if isinstance(item, dict) else {}
            if isinstance(meta, dict):
                if str(meta.get("memory_kind", "")).lower() == "profile_fact" and str(meta.get("field", "")).lower() == "name":
                    value = str(meta.get("value") or "").strip().strip(".,!?;:\"'")
                    if value:
                        return value

            text = str(item.get("text") if isinstance(item, dict) else "" or "")
            match = profile_pattern.search(text)
            if match:
                return match.group(1).strip().strip(".,!?;:\"'")
        return None

    def _summarize_task_start(self, user_text: str, steps: List[Any]) -> str:
        first_desc = ""
        if steps:
            first_desc = str(getattr(steps[0], "description", "") or "").strip()
        first_desc = re.sub(r"^\s*understand and execute:\s*", "", first_desc, flags=re.IGNORECASE)
        if "relevant past memories" in first_desc.lower():
            first_desc = ""
        first_desc = " ".join(first_desc.split())
        summary = first_desc or " ".join((user_text or "").strip().split())
        summary = summary[:180]
        return f"I've started a task with {len(steps)} steps: {summary}..."

    def _queue_preference_update(self, user_id: str, key: str, value: Any, source: str) -> None:
        if not self.preference_manager:
            return
        if not str(user_id or "").strip():
            return
        set_pref = getattr(self.preference_manager, "set", None)
        if callable(set_pref):
            asyncio.create_task(set_pref(user_id, key, value))
            logger.info(
                "preference_implicit_update_queued user_id=%s key=%s value=%s source=%s",
                user_id,
                key,
                value,
                source,
            )
            return
        update_pref = getattr(self.preference_manager, "update_preference", None)
        if callable(update_pref):
            asyncio.create_task(update_pref(user_id, key, value))
            logger.info(
                "preference_implicit_update_queued user_id=%s key=%s value=%s source=%s",
                user_id,
                key,
                value,
                source,
            )

    def _queue_preference_extraction(self, user_text: str, user_id: str) -> None:
        if not self.preference_manager:
            return
        extract = getattr(self.preference_manager, "extract_from_text", None)
        if callable(extract) and str(user_text or "").strip():
            asyncio.create_task(extract(user_text, user_id))

    def _capture_implicit_preference_from_direct_tool(
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
                    self._queue_preference_update(
                        user_id,
                        "preferred_browser",
                        browser,
                        source="direct_open_app",
                    )
                    break
            for music_app in ("spotify", "youtube", "vlc"):
                if music_app in app_name:
                    self._queue_preference_update(
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
                self._queue_preference_update(
                    user_id,
                    "preferred_volume",
                    percent,
                    source="direct_set_volume",
                )

    @staticmethod
    def _is_generic_music_request(message: str) -> bool:
        text = str(message or "").strip().lower()
        return bool(
            re.search(
                r"\b(play|start|put on)\b(?:\s+(?:some|any))?\s+\b(music|songs?)\b",
                text,
                re.IGNORECASE,
            )
        )

    async def _resolve_media_query_from_preferences(self, message: str, user_id: str) -> str:
        if not self.preference_manager:
            return message
        if not self._is_generic_music_request(message):
            return message

        get_pref = getattr(self.preference_manager, "get_all", None)
        if not callable(get_pref):
            get_pref = getattr(self.preference_manager, "get_preferences", None)
        if not callable(get_pref):
            return message

        try:
            prefs = await get_pref(user_id)
        except Exception as pref_err:
            logger.debug("media_preference_lookup_failed user_id=%s error=%s", user_id, pref_err)
            return message

        music_app = str((prefs or {}).get("music_app") or "").strip().lower()
        music_genre = str((prefs or {}).get("music_genre") or "").strip().lower()
        if not music_app or not music_genre:
            return message

        query = get_music_query(music_genre)
        logger.info("media_preference_resolved app=%s query=%s user_id=%s", music_app, query, user_id)
        return f"play {query} on {music_app}"

    def _detect_direct_tool_intent(self, message: str, origin: str = "chat") -> Optional[DirectToolIntent]:
        """
        Deterministic fast-path for high-frequency queries.
        Avoids LLM roundtrip and prevents 'thinking forever' on trivial time/date asks.
        """
        text = (message or "").strip().lower()
        normalized = re.sub(r"\s+", " ", text).strip()
        normalized = re.sub(r"[.,!?]+", "", normalized).strip()
        logger.debug(
            "fast_path_classification_input origin=%s input_length=%d has_bootstrap_marker=%s preview='%s'",
            origin,
            len(message or ""),
            "\n\ncurrent user message:\n" in text,
            (message or "")[:80].replace("\n", "\\n"),
        )

        if self._is_recall_exclusion_intent(text):
            logger.info("🧭 routing_mode=planner recall_exclusion=true origin=%s", origin)
            return None

        time_patterns = (
            r"\bwhat(?:'s| is)?\s+(?:the\s+)?time\b",
            r"\bcurrent\s+time\b",
            r"\btime\s+now\b",
            r"\bwhat\s+time\s+is\s+it\b",
            r"\bcan you tell me the time\b",
            r"\bdo you know (?:what|the) time\b",
            r"\btell me the time\b",
            r"\bwhat(?:'s| is) the (?:current )?time\b",
            r"\btime (?:is it|now)\b",
        )
        if any(re.search(p, text) for p in time_patterns):
            return DirectToolIntent("get_time", {}, "Here's the current time.", "time")

        date_patterns = (
            r"\bwhat(?:'s| is)?\s+(?:the\s+)?date\b",
            r"\btoday'?s\s+date\b",
            r"\bwhat\s+day\s+is\s+it\b",
        )
        if any(re.search(p, text) for p in date_patterns):
            return DirectToolIntent("get_date", {}, "Here's today's date.", "time")

        raw_message = (message or "").strip()
        note_create_match = re.match(
            r"^\s*create\s+(?:a\s+)?note(?:\s+titled)?\s+(?P<title>.+?)\s+with\s+content\s+(?P<content>.+)\s*$",
            raw_message,
            re.IGNORECASE,
        )
        if note_create_match:
            title = note_create_match.group("title").strip().strip("\"'")
            content = note_create_match.group("content").strip().strip("\"'")
            if title and content:
                return DirectToolIntent(
                    "create_note",
                    {"title": title, "content": content},
                    f"I've created note '{title}'.",
                    "notes",
                )

        note_read_match = re.match(
            r"^\s*(?:read|show)\s+(?:my\s+)?note\s+(?P<title>.+)\s*$",
            raw_message,
            re.IGNORECASE,
        )
        if note_read_match:
            title = note_read_match.group("title").strip().strip("\"'")
            if title:
                return DirectToolIntent("read_note", {"title": title}, f"Reading note '{title}'.", "notes")

        note_delete_match = re.match(
            r"^\s*delete\s+(?:my\s+)?note\s+(?P<title>.+)\s*$",
            raw_message,
            re.IGNORECASE,
        )
        if note_delete_match:
            title = note_delete_match.group("title").strip().strip("\"'")
            if title:
                return DirectToolIntent("delete_note", {"title": title}, f"Deleted note '{title}'.", "notes")

        if re.match(r"^\s*(?:list|show)\s+(?:my\s+)?notes\s*$", raw_message, re.IGNORECASE):
            return DirectToolIntent("list_notes", {}, "Here are your notes.", "notes")

        # Group 1: media controls
        if re.search(r"\b(next|skip|change)\b.{0,15}\b(song|track|music)\b", normalized, re.IGNORECASE):
            return DirectToolIntent("run_shell_command", {"command": "playerctl next"}, "Next track.", "media")
        if re.search(r"\b(previous|prev|go back|last)\b.{0,15}\b(song|track|music)\b", normalized, re.IGNORECASE):
            return DirectToolIntent("run_shell_command", {"command": "playerctl previous"}, "Previous track.", "media")
        if re.match(r"^\s*play\s+next(?:\s+(?:song|track|music))?\s*$", normalized, re.IGNORECASE):
            return DirectToolIntent("run_shell_command", {"command": "playerctl next"}, "Next track.", "media")
        if re.match(
            r"^\s*play\s+previous(?:\s+(?:song|track|music))?\s*$",
            normalized,
            re.IGNORECASE,
        ):
            return DirectToolIntent("run_shell_command", {"command": "playerctl previous"}, "Previous track.", "media")
        if re.match(r"^\s*(pause|pause (the )?(music|song|playback))\s*$", normalized, re.IGNORECASE):
            return DirectToolIntent("run_shell_command", {"command": "playerctl pause"}, "Paused.", "media")
        if re.match(r"^\s*(resume|continue playing|resume music)\s*$", normalized, re.IGNORECASE):
            return DirectToolIntent("run_shell_command", {"command": "playerctl play"}, "Playing.", "media")
        if re.match(r"^\s*(stop|stop music|stop song|stop playback)\s*$", normalized, re.IGNORECASE):
            return DirectToolIntent("run_shell_command", {"command": "playerctl stop"}, "Stopped.", "media")
        if re.match(r"^\s*(volume up|increase volume|turn volume up|louder)\s*$", normalized, re.IGNORECASE):
            return DirectToolIntent("run_shell_command", {"command": "playerctl volume 0.1+"}, "Volume up.", "media")
        if re.match(r"^\s*(volume down|decrease volume|turn volume down|quieter)\s*$", normalized, re.IGNORECASE):
            return DirectToolIntent("run_shell_command", {"command": "playerctl volume 0.1-"}, "Volume down.", "media")
        if re.match(r"^\s*(mute|mute music|mute playback)\s*$", normalized, re.IGNORECASE):
            return DirectToolIntent("run_shell_command", {"command": "playerctl volume 0.0"}, "Muted.", "media")
        volume_set = re.match(
            r"^\s*(?:set|change|adjust)(?:\s+the)?\s+volume(?:\s+to)?\s+(\d{1,3})\s*%?\s*$",
            normalized,
            re.IGNORECASE,
        )
        if volume_set:
            percent = max(0, min(100, int(volume_set.group(1))))
            return DirectToolIntent(
                "set_volume",
                {"percent": percent},
                f"Set volume to {percent}%.",
                "media",
            )

        # Group 2: YouTube open + search
        yt_search = re.match(
            r"^(open youtube and search|search youtube)\s+for\s+(.+)$",
            normalized,
            re.IGNORECASE,
        )
        if yt_search:
            query = (yt_search.group(2) or "").strip()
            if query:
                self.turn_state["last_search_target"] = "youtube"
                self.turn_state["last_search_query"] = query
                return DirectToolIntent(
                    "open_app",
                    {"app_name": f"youtube search for {query}"},
                    f"Searching YouTube for {query}.",
                    "youtube",
                )
        if re.match(r"^open youtube\s*$", normalized, re.IGNORECASE):
            self.turn_state["last_search_target"] = "youtube"
            return DirectToolIntent("open_app", {"app_name": "youtube"}, "Opening YouTube.", "youtube")

        # Group 4: folder open via xdg-open
        folder_match = re.match(
            r"^open\s+(?:my\s+)?(downloads|documents|desktop|home|pictures|videos)(?:\s+folder)?\s*$",
            normalized,
            re.IGNORECASE,
        )
        if folder_match:
            folder = folder_match.group(1).strip().lower()
            home = os.path.expanduser("~")
            folder_map = {
                "downloads": os.path.join(home, "Downloads"),
                "documents": os.path.join(home, "Documents"),
                "desktop": os.path.join(home, "Desktop"),
                "home": home,
                "pictures": os.path.join(home, "Pictures"),
                "videos": os.path.join(home, "Videos"),
            }
            folder_path = folder_map.get(folder, home)
            return DirectToolIntent(
                "run_shell_command",
                {"command": f"xdg-open '{folder_path}'"},
                f"Opened {folder.capitalize()} folder.",
                "app",
            )

        yt_alt_search = re.match(r"^\s*(?:in|on)?\s*youtube\s+search\s+for\s+(.+)$", normalized, re.IGNORECASE)
        if yt_alt_search:
            query = (yt_alt_search.group(1) or "").strip()
            if query:
                return DirectToolIntent(
                    "open_app",
                    {"app_name": f"youtube search for {query}"},
                    f"Searching YouTube for {query}.",
                    "youtube",
                )

        open_app_patterns = (
            r"^\s*(?:open|launch|start)\s+(.+)$",
            r"^\s*open\s+the\s+(.+)$",
        )
        for pat in open_app_patterns:
            m = re.search(pat, text)
            if m:
                app_name = (m.group(1) or "").strip()
                if app_name:
                    multi_app_commands = self._parse_multi_app(app_name)
                    if multi_app_commands:
                        return DirectToolIntent(
                            "run_shell_command",
                            {"commands": multi_app_commands},
                            f"Opening {app_name}.",
                            "app",
                        )
                    return DirectToolIntent("open_app", {"app_name": app_name}, f"Opening {app_name}.", "app")

        close_app_patterns = (
            r"^\s*(?:close|quit|exit|stop)\s+(.+)$",
            r"^\s*close\s+the\s+(.+)$",
        )
        for pat in close_app_patterns:
            m = re.search(pat, text)
            if m:
                app_name = (m.group(1) or "").strip()
                if app_name:
                    return DirectToolIntent("close_app", {"app_name": app_name}, f"Closing {app_name}.", "app")

        return None

    async def _execute_tool_call(
        self,
        tool_name: str,
        args: Dict[str, Any],
        user_id: str,
        tool_context: Any = None,
    ) -> tuple[Any, "ToolInvocation"]:
        """Execute one tool through the router with governance context."""
        from core.response.agent_response import ToolInvocation
        import time

        router = get_router()
        logger.info(f"🔧 CHAT path executing tool: {tool_name}({args})")
        if not router.tool_executor:
            return (
                self._normalize_tool_result(
                    tool_name=tool_name,
                    raw_result=None,
                    error_code="tool_not_wired",
                ),
                ToolInvocation(tool_name=tool_name, status="failed", latency_ms=None),
            )

        if tool_context is None:
            default_role = _coerce_user_role(
                getattr(settings, "default_client_role", "USER"),
                default_role=UserRole.USER,
            )
            tool_context = type(
                "ToolExecutionContext",
                (),
                {
                    "user_id": user_id,
                    "user_role": default_role,
                    "room": self.room,
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
            result = self._normalize_tool_result(
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
                self._normalize_tool_result(
                    tool_name=tool_name,
                    raw_result=None,
                    error_code="tool_exception",
                ),
                ToolInvocation(tool_name=tool_name, status="failed", latency_ms=latency_ms),
            )

    def _normalize_tool_result(
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
        if self._TOOL_ERROR_HINT_PATTERN.search(text):
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

    async def _generate_voice_text(self, role_llm: Any, display_text: str) -> str:
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
            response_text, synthesis_status = await self._run_theless_synthesis_with_timeout(
                chat_ctx,
                role_llm=role_llm,
            )
            self._record_synthesis_metrics(
                synthesis_status=synthesis_status,
                fallback_used=not bool((response_text or "").strip()),
                fallback_source="generic_ack" if not (response_text or "").strip() else "none",
                tool_name="voice_summary",
                mode="voice_summary",
            )
            return response_text.strip()
        except Exception as e:
            logger.warning(f"⚠️ Voice summary generation failed: {e}")
            return ""

    async def _run_theless_synthesis_with_timeout(
        self,
        chat_ctx: Any,
        role_llm: Any = None,
    ) -> tuple[str, str]:
        try:
            text = await asyncio.wait_for(
                self._run_theless_synthesis(chat_ctx, role_llm=role_llm),
                timeout=self._synthesis_timeout_s,
            )
            return text, "ok"
        except asyncio.TimeoutError:
            return "", "timeout"
        except Exception:
            return "", "error"

    async def _run_theless_synthesis(self, chat_ctx: Any, role_llm: Any = None) -> str:
        """
        Execute synthesis with an isolated tool-less model path.
        Planner tooling must never leak here.
        """
        stream = None
        response_text = ""
        try:
            base_llm = getattr(getattr(self.agent, "smart_llm", None), "base_llm", None)
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

    def _record_synthesis_metrics(
        self,
        *,
        synthesis_status: str,
        fallback_used: bool,
        fallback_source: str,
        tool_name: str,
        mode: str,
    ) -> None:
        self._synthesis_total += 1
        if synthesis_status == "timeout":
            self._synthesis_timeout_total += 1
        if fallback_used:
            self._synthesis_fallback_total += 1
        self._synthesis_fallback_window.append(bool(fallback_used))
        fallback_rate = (
            sum(1 for x in self._synthesis_fallback_window if x)
            / float(len(self._synthesis_fallback_window))
            if self._synthesis_fallback_window
            else 0.0
        )
        logger.info(
            "🧪 synthesis_status=%s synthesis_timeout_s=%.2f synthesis_fallback_used=%s "
            "synthesis_fallback_source=%s synthesis_total=%s synthesis_timeout_total=%s "
            "synthesis_fallback_total=%s synthesis_fallback_rate_last_n=%.3f tool_name=%s mode=%s",
            synthesis_status,
            self._synthesis_timeout_s,
            fallback_used,
            fallback_source,
            self._synthesis_total,
            self._synthesis_timeout_total,
            self._synthesis_fallback_total,
            fallback_rate,
            tool_name,
            mode,
        )
        if fallback_rate > self._synthesis_fallback_warn_rate:
            logger.warning(
                "⚠️ SYNTHESIS_FALLBACK_RATE_HIGH rate=%.3f window=%s",
                fallback_rate,
                len(self._synthesis_fallback_window),
            )

    def _get_tool_response_template(
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

    async def _build_agent_response(
        self,
        role_llm: Any,
        raw_output: str,
        *,
        mode: str = "normal",
        tool_invocations: Optional[List[ToolInvocation]] = None,
        structured_data: Optional[Dict[str, Any]] = None,
    ) -> AgentResponse:
        sanitized_output = self._sanitize_response(raw_output)
        parsed = ResponseFormatter.parse_agent_response_json(sanitized_output)
        response = ResponseFormatter.normalize_response(
            parsed if parsed else sanitized_output,
            tool_invocations=tool_invocations,
            mode=mode,
            structured_data=structured_data,
        )
        clean_display = self._sanitize_response(response.display_text)
        clean_voice = self._sanitize_response(response.voice_text)
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
        return response

    def _safe_json_dump(self, data: Any) -> str:
        try:
            return json.dumps(data, ensure_ascii=False)
        except Exception:
            return json.dumps(str(data), ensure_ascii=False)

    async def _synthesize_tool_response(
        self,
        role_llm: Any,
        user_message: str,
        tool_name: str,
        tool_output: Any,
        tool_invocation: ToolInvocation,
        mode: str = "normal",
    ) -> AgentResponse:
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
            return self._tag_response_with_routing_type(
                response,
                self._classify_tool_intent_type(tool_name),
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
            f"Tool output: {self._safe_json_dump(structured_data)}"
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
            synthesis, synthesis_status = await self._run_theless_synthesis_with_timeout(
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
                template = self._get_tool_response_template(tool_name, structured_data, mode=mode)
                if template:
                    synthesis = template
                    fallback_source = "tool_template"
                else:
                    synthesis = "I completed the action."
                    fallback_source = "generic_ack"
            synthesis_fallback_used = True

        response = await self._build_agent_response(
            role_llm,
            synthesis,
            mode=mode,
            tool_invocations=[tool_invocation],
            structured_data=structured_data,
        )
        self._record_synthesis_metrics(
            synthesis_status=synthesis_status,
            fallback_used=synthesis_fallback_used,
            fallback_source=fallback_source,
            tool_name=tool_name,
            mode=mode,
        )
        response = self._tag_response_with_routing_type(
            response,
            self._classify_tool_intent_type(tool_name),
        )
        if sources:
            response.sources = sources
        return response

    async def _build_direct_tool_response(
        self,
        role_llm: Any,
        tool_output: Any,
        tool_invocation: ToolInvocation,
    ) -> AgentResponse:
        structured_data = tool_output if isinstance(tool_output, dict) else {"result": str(tool_output or "")}
        raw_text = ResponseFormatter.extract_display_candidate(structured_data, tool_invocation.tool_name) or ""
        if not raw_text:
            raw_text = self._get_tool_response_template(
                tool_invocation.tool_name,
                structured_data,
                mode="direct",
            ) or "I completed the action."
        response = await self._build_agent_response(
            role_llm,
            raw_text,
            mode="direct",
            tool_invocations=[tool_invocation],
            structured_data=structured_data,
        )
        return self._tag_response_with_routing_type(
            response,
            self._classify_tool_intent_type(tool_invocation.tool_name),
        )

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
            # 0. Safety Check
            if self.context_guard:
                if self.context_guard.count_tokens(message) > 2000:
                    msg = "I'm sorry, that request is too long for me to process safely."
                    await self._announce(msg)
                    return ResponseFormatter.build_response(msg, mode="safe")

            if self._is_malformed_short_request(message):
                return ResponseFormatter.build_response(
                    "I can help with tasks, reminders, notes, or calendar events. "
                    "Please rephrase your request in one simple sentence."
                )

            # Phase <= 3 keeps chat/tool-only route.
            if not self.enable_task_pipeline:
                return await self._handle_chat_response(
                    effective_message,
                    user_id,
                    tool_context=tool_context,
                    origin=origin,
                )

            # 1. Check for Active Task
            active_tasks = await self._maybe_await(self.task_store.get_active_tasks(user_id))
            if active_tasks:
                logger.info(f"🔄 Active task found for {user_id}: {len(active_tasks)}")
                if any(k in message.lower() for k in ("status", "progress", "how far", "done")):
                    first = active_tasks[0]
                    total_steps = max(len(first.steps), 1)
                    current_step_display = min(first.current_step_index + 1, total_steps)
                    return ResponseFormatter.build_response(
                        f"You have {len(active_tasks)} active task(s). "
                        f"Current: '{first.title}' step {current_step_display}/{total_steps}."
                    )

            # 2. Intent Classification
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
            
            # Use normalization for intent logging/routing safety
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
                return response
            else:
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
                return response

        except Exception as e:
            logger.error(f"❌ Error handling message: {e}")
            return ResponseFormatter.build_response("Something went wrong processing your request.")

    async def handle_intent(self, message: str, user_id: str = "test_user") -> AgentResponse:
        """
        Backward-compatible alias for older test/util paths.
        """
        logger.warning("⚠️ handle_intent() is deprecated; routing via handle_message().")
        if self.context_guard and self.context_guard.count_tokens(message) > 2000:
            msg = "I'm sorry, that request is too long for me to process safely."
            await self._announce(msg)
            return ResponseFormatter.build_response(msg, mode="safe")
        return await self.handle_message(message, user_id)

    async def _handle_task_request(
        self,
        user_text: str,
        user_id: str,
        tool_context: Any = None,
    ) -> str:
        """Handle execution via PLANNER role."""
        report_export_result = await self._try_handle_report_export_task(
            user_text=user_text,
            user_id=user_id,
            tool_context=tool_context,
        )
        if report_export_result is not None:
            return report_export_result

        planning_task_id = getattr(tool_context, "task_id", None) or f"handoff-plan:{uuid.uuid4()}"
        host_profile = self._get_host_capability_profile(refresh=True)
        handoff_target = self._consume_handoff_signal(
            target_agent="planner",
            execution_mode="planning",
            reason="task_request_detected",
            context_hint=str(user_text or "")[:160],
        )
        handoff_request = self._build_handoff_request(
            target_agent=handoff_target,
            message=user_text,
            user_id=user_id,
            execution_mode="planning",
            tool_context=tool_context,
            handoff_reason="task_request_detected",
            force_task_id=planning_task_id,
            host_profile=host_profile,
        )
        handoff_result = await self._handoff_manager.delegate(handoff_request)
        if handoff_result.status == "failed":
            return "I couldn't start planning that request safely."

        session_id = getattr(getattr(self, "room", None), "name", None) or "console_session"
        set_trace_context(
            trace_id=current_trace_id(),
            session_id=session_id,
            user_id=user_id,
        )

        # 1. Retrieve Context
        memory_session_id = getattr(getattr(self, "room", None), "name", None) or session_id
        memory_context = await self._retrieve_memory_context_async(
            user_text,
            origin="chat",
            routing_mode_type="informational",
            user_id=user_id,
            session_id=memory_session_id,
        )
        augmented_sections: List[str] = []
        if host_profile:
            augmented_sections.append(self._host_profile_to_text(host_profile))
        if memory_context:
            augmented_sections.append(memory_context)
            augmented_sections.append(f"User Request: {user_text}")
        else:
            augmented_sections.append(user_text)
        augmented_text = "\n".join(section for section in augmented_sections if section)
        
        logger.info(f"🤔 Planning task for: {user_text}")
        if not str(user_id).startswith("livekit:"):
            await self._announce(f"I'm planning how to handle: {user_text}")
        
        # 2. Generate and validate plan via canonical TaskPlan repair layer.
        plan_result = None
        plan_result_call = getattr(self.planning_engine, "generate_plan_result", None)
        if (
            inspect.ismethod(plan_result_call)
            or inspect.isfunction(plan_result_call)
            or inspect.iscoroutinefunction(plan_result_call)
        ):
            maybe_plan_result = plan_result_call(augmented_text)
            if hasattr(maybe_plan_result, "__await__"):
                plan_result = await maybe_plan_result

        if plan_result is None:
            steps_legacy = await self.planning_engine.generate_plan(augmented_text)
            plan_result = type(
                "PlanResult",
                (),
                {
                    "steps": steps_legacy,
                    "plan_failed": False,
                    "error_payload": None,
                },
            )()

        steps = plan_result.steps

        if not steps and not plan_result.plan_failed:
            return "I couldn't create a plan for that request."

        task_status = TaskStatus.PLAN_FAILED if plan_result.plan_failed else TaskStatus.PENDING

        # 3. Create Task
        task = Task(
            user_id=user_id,
            title=f"Task: {user_text[:30]}...",
            description=user_text,
            steps=steps,
            status=task_status,
        )
        precreate_trace = get_trace_context()
        default_role = _coerce_user_role(
            getattr(settings, "default_client_role", "USER"),
            default_role=UserRole.USER,
        )
        task.metadata = task.metadata or {}
        task.metadata["trace_id"] = precreate_trace.get("trace_id")
        task.metadata["session_id"] = precreate_trace.get("session_id")
        task.metadata["user_role"] = default_role.name
        turn_id = None
        if tool_context is not None:
            turn_id = getattr(tool_context, "turn_id", None)
        if not turn_id:
            turn_id = (self.turn_state or {}).get("current_turn_id")
        if turn_id:
            task.metadata["turn_id"] = turn_id
        if tool_context is not None:
            ctx_trace_id = getattr(tool_context, "trace_id", None)
            if ctx_trace_id:
                task.metadata["trace_id"] = ctx_trace_id
            ctx_session_id = getattr(tool_context, "session_id", None)
            if ctx_session_id:
                task.metadata["session_id"] = ctx_session_id
            ctx_conversation_id = getattr(tool_context, "conversation_id", None)
            if ctx_conversation_id:
                task.metadata["conversation_id"] = ctx_conversation_id
            participant_metadata = getattr(tool_context, "participant_metadata", None)
            if isinstance(participant_metadata, dict):
                meta_conversation_id = str(participant_metadata.get("conversation_id") or "").strip()
                if meta_conversation_id:
                    task.metadata["conversation_id"] = meta_conversation_id
        if plan_result.plan_failed and plan_result.error_payload:
            task.metadata["planner_error"] = plan_result.error_payload
        planner_taskplan_json = getattr(plan_result, "raw_response", None)
        if planner_taskplan_json:
            task.metadata["planner_taskplan_json"] = planner_taskplan_json

        success = await self._maybe_await(self.task_store.create_task(task))
        if success:
            trace_ctx = set_trace_context(task_id=task.id)
            if plan_result.plan_failed:
                self.turn_state["pending_task_completion_summary"] = "I wasn't able to plan that task."
                structured_error = {
                    "event": "planner_plan_failed",
                    "task_id": task.id,
                    "trace_id": trace_ctx.get("trace_id"),
                    "attempts": (plan_result.error_payload or {}).get("attempt_count"),
                    "issues": (plan_result.error_payload or {}).get("issues", []),
                }
                logger.error(f"❌ PLAN_FAILED {structured_error}")
                await self._maybe_await(
                    self.task_store.add_log(task.id, f"PLAN_FAILED: {structured_error}")
                )
                await self._handle_task_worker_event(
                    {
                        "event_type": "plan_failed",
                        "task_id": task.id,
                        "trace_id": trace_ctx.get("trace_id"),
                        "message": "I wasn't able to plan that task.",
                        "voice_text": "I wasn't able to plan that task.",
                    }
                )
                return "I couldn't create a safe executable plan for that request."

            await self._ensure_task_worker(user_id)
            RuntimeMetrics.increment("tasks_created_total")
            logger.info(
                f"✅ Task {task.id} created with {len(steps)} steps "
                f"(trace_id={trace_ctx.get('trace_id')})."
            )
            
            response = self._summarize_task_start(user_text, steps)
            self.turn_state["pending_task_completion_summary"] = response
            
            # Store turn in background to avoid blocking the turn loop.
            asyncio.create_task(
                self.memory.store_conversation_turn(
                    user_msg=user_text,
                    assistant_msg=response,
                    metadata={"source": "conversation", "role": "planner"},
                    user_id=user_id,
                    session_id=memory_session_id,
                )
            )
            return response
        else:
            return "Failed to save the task."

    async def _try_handle_report_export_task(
        self,
        *,
        user_text: str,
        user_id: str,
        tool_context: Any = None,
    ) -> str | None:
        if not self._is_report_export_request(user_text):
            return None

        user_role = _coerce_user_role(
            getattr(tool_context, "user_role", None) if tool_context is not None else None,
            default_role=UserRole.USER,
        )
        if user_role < UserRole.TRUSTED:
            return (
                "I can prepare the report summary, but saving files to Downloads needs TRUSTED role. "
                "Enable TRUSTED role in client metadata and retry."
            )

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
        research_query = self._extract_report_focus_query(user_text)
        if not research_query:
            research_query = user_text

        try:
            research_result = await self._run_inline_research_pipeline(
                query=research_query,
                user_id=user_id,
                session_id=session_id,
                trace_id=trace_id,
            )
        except Exception as exc:
            logger.error("report_export_research_failed error=%s", exc, exc_info=True)
            return "I couldn't prepare the report content yet. Please try again."

        if not research_result or not str(getattr(research_result, "summary", "")).strip():
            return "I couldn't prepare a reliable report summary right now."

        output_path = self._build_report_output_path(research_query)
        report_markdown = self._compose_report_markdown(
            query=research_query,
            summary=str(research_result.summary or "").strip(),
            sources=list(getattr(research_result, "sources", []) or []),
        )
        result, invocation = await self._execute_tool_call(
            "create_docx",
            {"content": report_markdown, "path": output_path},
            user_id,
            tool_context=tool_context,
        )
        if invocation.status != "success":
            result_message = str((result or {}).get("message") or "").strip()
            if "permission denied" in result_message.lower() or "access denied" in result_message.lower():
                return (
                    "Report content is ready, but I don't have permission to save in Downloads. "
                    "Use TRUSTED role and retry."
                )
            return (
                "I prepared the report content, but saving the document failed. "
                "Please retry once."
            )

        return (
            f"I created a report and saved it to {output_path}. "
            f"Sources included: {len(getattr(research_result, 'sources', []) or [])}."
        )

    @staticmethod
    def _compose_report_markdown(query: str, summary: str, sources: list[Any]) -> str:
        lines = [
            f"# Research Report: {query}",
            "",
            "## Executive Summary",
            summary or "No summary available.",
            "",
            "## Sources",
        ]
        if sources:
            for idx, source in enumerate(sources[:12], start=1):
                if hasattr(source, "title"):
                    title = str(getattr(source, "title", "") or f"Source {idx}")
                    url = str(getattr(source, "url", "") or "")
                    snippet = str(getattr(source, "snippet", "") or "").strip()
                else:
                    source_dict = source if isinstance(source, dict) else {}
                    title = str(source_dict.get("title") or f"Source {idx}")
                    url = str(source_dict.get("url") or "")
                    snippet = str(source_dict.get("snippet") or "").strip()
                line = f"- [{idx}] {title}"
                if url:
                    line += f" ({url})"
                if snippet:
                    line += f" - {snippet}"
                lines.append(line)
        else:
            lines.append("- No sources were available.")
        return "\n".join(lines).strip() + "\n"

    async def _ensure_task_worker(self, user_id: str) -> None:
        """
        Start one TaskWorker per user for phase-4 task execution.
        """
        async with self._task_worker_lock:
            existing = self._task_workers.get(user_id)
            if existing and getattr(existing, "is_running", False):
                if getattr(self, "room", None) is not None:
                    existing.set_room(self.room)
                return

            from core.tasks.task_worker import TaskWorker

            smart_llm = getattr(self.agent, "smart_llm", None)
            worker = TaskWorker(
                user_id=user_id,
                memory_manager=self.memory,
                smart_llm=smart_llm,
                room=getattr(self, "room", None),
                event_notifier=self._handle_task_worker_event,
            )
            await worker.start()
            self._task_workers[user_id] = worker
            logger.info(f"👷 TaskWorker started for {user_id}")

    async def shutdown(self) -> None:
        """Stop background task workers started by this orchestrator."""
        async with self._task_worker_lock:
            workers = list(self._task_workers.values())
            self._task_workers.clear()

        for worker in workers:
            try:
                await worker.stop()
            except Exception as e:
                logger.warning(f"⚠️ Failed to stop TaskWorker cleanly: {e}")

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

    def _resolve_session_queue_key(self, tool_context: Any = None) -> str:
        return (
            getattr(tool_context, "session_id", None)
            or self._current_session_id
            or getattr(getattr(self, "room", None), "name", None)
            or "console_session"
        )

    def _queue_rejection_response(self) -> AgentResponse:
        response = ResponseFormatter.build_response(
            "I'm still working on previous requests. Please try again."
        )
        return self._tag_response_with_routing_type(response, "informational")

    async def _store_chat_turn_memory(
        self,
        user_text: str,
        response: Any,
        user_id: str = "console_user",
        session_id: str | None = None,
        origin: str = "chat",
    ) -> None:
        """Best-effort chat memory write for every chat response path."""
        response_text = ""
        if isinstance(response, AgentResponse):
            response_text = str(response.display_text or response.voice_text or "").strip()
        else:
            response_text = str(response or "").strip()

        if not response_text:
            return
        if response_text.startswith("Sorry, I encountered"):
            return

        store_turn = getattr(self.memory, "store_conversation_turn", None)
        if not callable(store_turn):
            logger.debug("chat_turn_memory_skipped reason=store_method_missing")
            return

        try:
            asyncio.create_task(
                store_turn(
                    user_msg=user_text,
                    assistant_msg=response_text,
                    metadata={"source": "conversation", "role": "chat"},
                    user_id=user_id,
                    session_id=session_id,
                )
            )
        except Exception as mem_err:
            logger.warning(f"⚠️ Failed to queue chat memory write: {mem_err}")
            return
        self._queue_preference_extraction(user_text, user_id)
        logger.info(
            "chat_turn_memory_stored user_id=%s session_id=%s origin=%s",
            user_id,
            session_id or "none",
            origin or "unknown",
        )

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

    async def _announce(self, message: str):
        """Helper to speak/announce via session if available."""
        if self.session:
            await self.session.say(message)

if __name__ == "__main__":
    import os
    import logging
    logging.basicConfig(level=logging.INFO)
    print("🚀 AgentOrchestrator standalone mode (Validation Only)")
    
    async def run_forever():
        try:
            while True:
                await asyncio.sleep(3600)
        except KeyboardInterrupt:
            pass
    
    asyncio.run(run_forever())
