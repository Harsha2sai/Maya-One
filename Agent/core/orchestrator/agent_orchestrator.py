
import logging
import asyncio
import uuid
import re
import inspect
import os
import json
import time
from collections import deque
from datetime import datetime, timezone
from typing import Any, Dict, Optional, List
from core.action.state_store import ActionStateStore
from core.action.models import ActionIntent, ToolReceipt
from core.tasks.planning_engine import PlanningEngine
from core.tasks.task_store import TaskStore
from core.context.context_guard import ContextGuard
from core.memory.hybrid_memory_manager import HybridMemoryManager
from core.memory.preference_manager import PreferenceManager
from core.orchestrator.agent_router import AgentRouter
from core.orchestrator.chat_mixin import ChatResponseMixin
from core.orchestrator.fast_path_router import FastPathRouter, DirectToolIntent
from core.orchestrator.media_resolver import MediaResolver
from core.orchestrator.orchestration_flow import OrchestrationFlow
from core.orchestrator.pronoun_rewriter import PronounRewriter
from core.orchestrator.research_handler import ResearchHandler
from core.orchestrator.media_handler import MediaHandler
from core.orchestrator.memory_context_service import MemoryContextService
from core.orchestrator.scheduling_handler import SchedulingHandler
from core.orchestrator.response_synthesizer import ResponseSynthesizer
from core.orchestrator.tool_executor import ToolExecutor
from core.orchestrator.tool_response_builder import ToolResponseBuilder
from core.orchestrator.task_runtime_service import TaskRuntimeService
from core.tools.livekit_tool_adapter import adapt_tool_list
from core.routing.router import get_router
from core.security.input_guard import InputGuard
from core.governance.types import UserRole
from core.utils.intent_utils import normalize_intent
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


class AgentOrchestrator(OrchestrationFlow, ChatResponseMixin):
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
            "last_route": "",
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
        self._session_queue_limit = max(1, int(os.getenv("MAYA_CHAT_SESSION_QUEUE_LIMIT", "3")))
        self._session_bootstrap_contexts: Dict[str, Dict[str, Any]] = {}
        self._last_research_contexts: Dict[str, Dict[str, Any]] = {}
        self._research_context_ttl_s = max(
            10.0,
            float(os.getenv("RESEARCH_CONTEXT_TTL_S", "900")),
        )
        self._voice_fragment_buffer_window_s = max(
            1.0,
            float(os.getenv("VOICE_FRAGMENT_BUFFER_WINDOW_S", "5")),
        )
        self._voice_fragment_buffer_window_research_s = max(
            self._voice_fragment_buffer_window_s,
            float(os.getenv("VOICE_FRAGMENT_BUFFER_WINDOW_RESEARCH_S", "8")),
        )
        self._research_handler = ResearchHandler(
            context_ttl_s=self._research_context_ttl_s,
            get_conversation_history=lambda: self._conversation_history,
            spawn_background_task=self._spawn_background_task,
            owner=self,
        )
        self._media_handler = MediaHandler(owner=self)
        self._scheduling_handler = SchedulingHandler(owner=self)
        self._enable_research_llm_planner = self._is_truthy_env(
            os.getenv("ENABLE_RESEARCH_LLM_PLANNER", "false")
        )
        self._action_receipts_enabled = bool(getattr(settings, "action_receipts_enabled", False))
        self._action_state_carryover_enabled = bool(
            getattr(settings, "action_state_carryover_enabled", False)
        )
        self._action_verification_enabled = bool(getattr(settings, "action_verification_enabled", False))
        self._action_truthfulness_strict = bool(getattr(settings, "action_truthfulness_strict", False))
        self._action_state_store: Optional[ActionStateStore] = (
            ActionStateStore() if self._action_state_carryover_enabled else None
        )
        self._fast_path_router = FastPathRouter(
            turn_state=self.turn_state,
            parse_multi_app_fn=self._parse_multi_app,
            is_recall_exclusion_intent_fn=self._is_recall_exclusion_intent,
            resolve_active_subject_fn=self._resolve_active_subject_for_fast_path,
        )
        self._tool_response_builder = ToolResponseBuilder(owner=self)
        self._tool_executor = ToolExecutor(owner=self, coerce_user_role_fn=_coerce_user_role)
        self._media_resolver = MediaResolver(owner=self)
        self._memory_context_service = MemoryContextService(owner=self)
        self._response_synthesizer = ResponseSynthesizer(owner=self)
        self._task_runtime_service = TaskRuntimeService(owner=self, coerce_user_role_fn=_coerce_user_role)
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
            "action_reform_flags receipts=%s carryover=%s verification=%s strict=%s",
            self._action_receipts_enabled,
            self._action_state_carryover_enabled,
            self._action_verification_enabled,
            self._action_truthfulness_strict,
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
        "yeah",
        "yep",
        "yes",
        "no",
        "well",
        "actually",
        "anyway",
        "i",
        "just",
        "and",
        "but",
        "so",
        "then",
        "also",
        "that",
        "this",
        "it",
        "about",
        "mean",
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
    _VOICE_CONTINUATION_PATTERN = re.compile(
        r"^(yeah|yep|yes|no|well|actually|anyway|i mean|so|and then|about it|about that)\b",
        re.IGNORECASE,
    )
    _VOICE_INCOMPLETE_ENDING_PATTERN = re.compile(
        r"\b(and|or|but|so|because|for|to|in|on|with|about|then|where|when|who|what|how)\s*[.!?,'\"]*\s*$",
        re.IGNORECASE,
    )
    _IDENTITY_KEYWORDS = {
        "maya",
        "name",
        "who",
        "you",
        "your",
        "creator",
        "created",
        "built",
        "harsha",
    }
    _IDENTITY_LEADING_PATTERN = re.compile(
        r"^\s*(?:hi[, ]+)?(?:i(?:\s*am|'m)\s+maya(?:\s*,\s*your\s+(?:voice\s+)?assistant)?"
        r"(?:\s*(?:,|and)\s*(?:i(?:\s+was)?\s+(?:created|built)\s+by\s+harsha))?\.?\s*)+",
        re.IGNORECASE,
    )

    def _classify_tool_intent_type(self, tool_name: str) -> str:
        return self._tool_response_builder.classify_tool_intent_type(tool_name)

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
        # Backward-compatible wrapper: subject extraction logic lives in ResearchHandler.
        return self._research_handler._extract_subject_from_text(raw_text)

    def _session_key_for_context(self, tool_context: Any = None) -> str:
        return (
            getattr(tool_context, "session_id", None)
            or self._current_session_id
            or getattr(getattr(self, "room", None), "name", None)
            or "console_session"
        )

    def _extract_summary_sentence(self, summary: str) -> str:
        # Backward-compatible wrapper: summary extraction logic lives in ResearchHandler.
        return self._research_handler._extract_summary_sentence(summary)

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
            if self._action_state_carryover_enabled and self._action_state_store is not None:
                subject = str(active.get("subject") or "").strip()
                search_query = str(active.get("query") or query or "").strip()
                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(
                        self._action_state_store.set_active_subject(
                            session_key,
                            subject=subject,
                            query=search_query,
                        )
                    )
                except RuntimeError:
                    pass

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
        # Backward-compatible wrapper: route-filtered resolution logic lives in ResearchHandler.
        session_key = (
            getattr(tool_context, "session_id", None)
            or self._current_session_id
            or getattr(getattr(self, "room", None), "name", None)
            or ""
        )
        payload = self._session_bootstrap_contexts.get(str(session_key or "").strip()) or {}
        return self._research_handler.resolve_research_subject_from_context(
            research_context=self._get_active_research_context(tool_context),
            conversation_history=self._conversation_history,
            bootstrap_payload=payload,
        )

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

        # Delegate to main rewrite method. Restrict history scan to research route
        # to avoid non-research subject contamination in pre-router override.
        research_context = self._get_active_research_context(tool_context)
        return self._pronoun_rewriter.rewrite(
            query,
            conversation_history=self._conversation_history,
            research_context=research_context,
            tool_context=tool_context,
            history_route_filter="research",
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

    async def _handle_media_route(
        self,
        *,
        message: str,
        user_id: str,
        tool_context: Any,
    ) -> AgentResponse:
        """Backward-compatible wrapper that delegates media route handling."""
        return await self._media_handler.handle_media_route(
            message=message,
            user_id=user_id,
            tool_context=tool_context,
        )

    async def _handle_scheduling_route(
        self,
        *,
        message: str,
        user_id: str,
        tool_context: Any,
    ) -> AgentResponse:
        """Backward-compatible wrapper that delegates scheduling route handling."""
        return await self._scheduling_handler.handle_scheduling_route(
            message=message,
            user_id=user_id,
            tool_context=tool_context,
        )

    async def _handle_research_route(
        self,
        *,
        message: str,
        user_id: str,
        tool_context: Any,
        query_rewritten: bool = False,
        query_ambiguous: bool = False,
    ) -> AgentResponse:
        """Backward-compatible wrapper that delegates research route handling."""
        return await self._research_handler.handle_research_route(
            message=message,
            user_id=user_id,
            tool_context=tool_context,
            query_rewritten=query_rewritten,
            query_ambiguous=query_ambiguous,
            publish_agent_thinking_fn=publish_agent_thinking,
            publish_tool_execution_fn=publish_tool_execution,
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
        """Backward-compatible wrapper that delegates research background execution."""
        await self._research_handler.run_research_background(
            query=query,
            user_id=user_id,
            session_id=session_id,
            trace_id=trace_id,
            turn_id=turn_id,
            room=room,
            session=session,
            task_id=task_id,
            conversation_id=conversation_id,
            publish_tool_execution_fn=publish_tool_execution,
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
        handoff_id = str(uuid.uuid4())
        parent_handoff_id = getattr(tool_context, "handoff_id", None)
        incoming_chain_id = getattr(tool_context, "delegation_chain_id", None)
        delegation_chain_id = incoming_chain_id or f"chain_{trace_id}_{conversation_id or self._current_session_id or 'session'}"
        max_depth = int(getattr(self._handoff_manager, "max_depth", 2))
        depth_used = max(0, int(getattr(tool_context, "delegation_depth", 0) or 0))
        depth_budget = max(1, max_depth - depth_used)
        return AgentHandoffRequest(
            handoff_id=handoff_id,
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
            delegation_depth=depth_used,
            max_depth=max_depth,
            handoff_reason=handoff_reason,
            parent_handoff_id=parent_handoff_id,
            delegation_chain_id=delegation_chain_id,
            depth_used=depth_used,
            depth_budget=depth_budget,
            metadata={
                "user_id": user_id,
                "user_role": getattr(getattr(tool_context, "user_role", None), "name", None)
                or getattr(tool_context, "user_role", "USER"),
                "conversation_history": list(self._conversation_history[-5:]),
                "memory_context": "",
                "task_scope": "inline_untracked" if not task_id else "tracked",
                "host_profile": host_profile,
                "session_id": self._resolve_session_queue_key(tool_context),
                "visited_targets": [],
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

    async def _record_action_intent(self, *, session_id: str, intent: ActionIntent) -> None:
        if not self._action_state_carryover_enabled or self._action_state_store is None:
            return
        await self._action_state_store.record_intent(session_id, intent)

    async def _record_action_receipt(self, *, session_id: str, receipt: ToolReceipt) -> None:
        if not self._action_state_carryover_enabled or self._action_state_store is None:
            return
        await self._action_state_store.record_receipt(session_id, receipt)

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

    def _resolve_active_subject_for_fast_path(self, tool_context: Any = None) -> str:
        if self._action_state_carryover_enabled and self._action_state_store is not None:
            session_key = self._session_key_for_context(tool_context)
            candidate = self._action_state_store.resolve_pronoun_sync(session_key, "it")
            if candidate:
                return candidate
        return self._resolve_research_subject_from_context(tool_context)

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

    def _is_voice_immediate_command(self, text: str) -> bool:
        normalized = re.sub(r"\s+", " ", str(text or "").strip().lower())
        if not normalized:
            return False
        if normalized in self._VOICE_SHORT_COMMAND_ALLOWLIST:
            return True
        return bool(
            re.match(
                r"^(next|previous|pause|resume|stop|cancel|mute|volume (?:up|down)|yes|no)\b",
                normalized,
                flags=re.IGNORECASE,
            )
        )

    def _looks_like_voice_fragment(self, text: str) -> bool:
        normalized = re.sub(r"\s+", " ", str(text or "").strip().lower())
        if not normalized:
            return False
        if self._is_voice_immediate_command(normalized):
            return False
        if self._VOICE_CONTINUATION_PATTERN.search(normalized):
            return True
        tokens = re.findall(r"\b[\w'-]+\b", normalized)
        if 0 < len(tokens) <= 4:
            return True
        if self._VOICE_INCOMPLETE_ENDING_PATTERN.search(normalized):
            return True
        return False

    def _is_semantically_complete_utterance(self, text: str) -> bool:
        normalized = re.sub(r"\s+", " ", str(text or "").strip())
        if not normalized:
            return False
        if self._is_voice_immediate_command(normalized):
            return True
        has_terminal_punctuation = bool(re.search(r"[.!?]['\"]?\s*$", normalized))
        if has_terminal_punctuation and not self._VOICE_INCOMPLETE_ENDING_PATTERN.search(normalized):
            return True
        token_count = len(re.findall(r"\b[\w'-]+\b", normalized))
        return token_count >= 8 and not self._VOICE_INCOMPLETE_ENDING_PATTERN.search(normalized.lower())

    def _voice_fragment_window_seconds(self, text: str) -> float:
        normalized = re.sub(r"\s+", " ", str(text or "").strip().lower())
        if not normalized:
            return self._voice_fragment_buffer_window_s
        last_route = str(self.turn_state.get("last_route") or "").strip().lower()
        continuation_heavy = bool(
            re.search(r"\b(it|that|this|they|them|him|her|about it|about that|reason)\b", normalized)
        )
        if last_route == "research" or continuation_heavy:
            return self._voice_fragment_buffer_window_research_s
        return self._voice_fragment_buffer_window_s

    def _identity_keyword_ratio(self, message: str) -> float:
        tokens = [token.lower() for token in re.findall(r"[a-zA-Z']+", str(message or ""))]
        if not tokens:
            return 0.0
        matches = sum(1 for token in tokens if token in self._IDENTITY_KEYWORDS)
        return float(matches) / float(len(tokens))

    def _is_identity_dominant_query(self, message: str) -> bool:
        if self._is_name_query(message) or self._is_creator_query(message):
            return True
        return self._identity_keyword_ratio(message) >= 0.5

    def _strip_identity_preamble_if_needed(self, user_message: str, response_text: str) -> str:
        if self._is_identity_dominant_query(user_message):
            return str(response_text or "").strip()
        cleaned = str(response_text or "").strip()
        if not cleaned:
            return ""
        stripped = re.sub(self._IDENTITY_LEADING_PATTERN, "", cleaned).strip()
        stripped = re.sub(
            r"^\s*(?:hi[, ]+)?i(?:\s*am|'m)\s+maya(?:\s*,\s*your\s+(?:voice\s+)?assistant)?[,.]?\s*",
            "",
            stripped,
            flags=re.IGNORECASE,
        )
        stripped = re.sub(
            r"^\s*[,;:-]?\s*(?:and\s+)?i(?:\s+was)?\s+(?:created|built)\s+by\s+harsha[,.]?\s*",
            "",
            stripped,
            flags=re.IGNORECASE,
        )
        stripped = stripped.lstrip(" ,;:-").strip()
        if stripped and stripped != cleaned:
            logger.info("identity_preamble_stripped_for_non_identity_turn")
            return stripped
        return cleaned

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
        task_id = str((event or {}).get("task_id") or "").strip()
        trace_id = str((event or {}).get("trace_id") or current_trace_id()).strip()
        logger.info(
            "task_event_received event_type=%s task_id=%s trace_id=%s",
            event_type,
            task_id,
            trace_id,
        )
        message_bus = getattr(self, "_message_bus", None)
        if message_bus is not None:
            status = "in_progress"
            if event_type in {"task_completed"}:
                status = "completed"
            elif event_type in {"task_failed", "task_poisoned", "task_stale", "plan_failed"}:
                status = "failed"
            try:
                await message_bus.publish(
                    "agent.progress",
                    {
                        "phase": "execution",
                        "agent": "task_worker",
                        "status": status,
                        "percent": 100 if status != "in_progress" else 50,
                        "summary": message or event_type,
                        "session_id": self._current_session_id,
                        "event_type": event_type,
                    },
                    trace_id=trace_id,
                    task_id=task_id,
                    handoff_id=str((event or {}).get("handoff_id") or ""),
                    checkpoint_id=str((event or {}).get("checkpoint_id") or ""),
                )
            except Exception as bus_err:
                logger.warning(
                    "task_event_progress_publish_failed task_id=%s trace_id=%s error=%s",
                    task_id,
                    trace_id,
                    bus_err,
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
        return self._memory_context_service.retrieve_memories(
            user_input,
            k=k,
            user_id=user_id,
            session_id=session_id,
            origin=origin,
        )

    def _format_memory_context(self, memories: List[Dict[str, Any]]) -> str:
        return self._memory_context_service.format_memory_context(memories)

    def _retrieve_memory_context(
        self,
        user_input: str,
        k: int = 5,
        user_id: str | None = None,
        session_id: str | None = None,
        origin: str = "chat",
    ) -> str:
        return self._memory_context_service.retrieve_memory_context(
            user_input,
            k=k,
            user_id=user_id,
            session_id=session_id,
            origin=origin,
        )

    async def _run_sync_with_timeout(
        self,
        func: Any,
        *args: Any,
        timeout_s: float,
    ) -> Any:
        return await self._memory_context_service.run_sync_with_timeout(
            func,
            *args,
            timeout_s=timeout_s,
        )

    def _is_tool_focused_query(self, message: str) -> bool:
        return self._memory_context_service.is_tool_focused_query(message)

    def _is_memory_relevant(self, text: str) -> bool:
        return self._memory_context_service.is_memory_relevant(text)

    def _is_recall_exclusion_intent(self, text: str) -> bool:
        return self._memory_context_service.is_recall_exclusion_intent(text)

    def _should_skip_memory(
        self,
        text: str,
        origin: str,
        routing_mode_type: str,
    ) -> tuple[bool, str]:
        return self._memory_context_service.should_skip_memory(
            text,
            origin,
            routing_mode_type,
        )

    async def _retrieve_memory_context_async(
        self,
        user_input: str,
        *,
        origin: str = "chat",
        routing_mode_type: str = "informational",
        user_id: str | None = None,
        session_id: str | None = None,
    ) -> str:
        return await self._memory_context_service.retrieve_memory_context_async(
            user_input,
            origin=origin,
            routing_mode_type=routing_mode_type,
            user_id=user_id,
            session_id=session_id,
        )

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
        self._tool_executor.capture_implicit_preference_from_direct_tool(
            tool_name=tool_name,
            tool_args=tool_args,
            user_id=user_id,
        )

    @staticmethod
    def _is_generic_music_request(message: str) -> bool:
        return MediaResolver.is_generic_music_request(message)

    async def _resolve_media_query_from_preferences(self, message: str, user_id: str) -> str:
        return await self._media_resolver.resolve_media_query_from_preferences(message, user_id)

    def _detect_direct_tool_intent(self, message: str, origin: str = "chat") -> Optional[DirectToolIntent]:
        """Backward-compatible wrapper for deterministic fast-path routing."""
        return self._fast_path_router.detect_direct_tool_intent(message, origin=origin)

    async def _execute_tool_call(
        self,
        tool_name: str,
        args: Dict[str, Any],
        user_id: str,
        tool_context: Any = None,
    ) -> tuple[Any, "ToolInvocation"]:
        """Execute one tool through the router with governance context."""
        return await self._tool_executor.execute_tool_call(
            tool_name=tool_name,
            args=args,
            user_id=user_id,
            tool_context=tool_context,
        )

    def _normalize_tool_result(
        self,
        *,
        tool_name: str,
        raw_result: Any,
        error_code: Optional[str] = None,
    ) -> Dict[str, Any]:
        return self._tool_response_builder.normalize_tool_result(
            tool_name=tool_name,
            raw_result=raw_result,
            error_code=error_code,
        )

    async def _generate_voice_text(self, role_llm: Any, display_text: str) -> str:
        return await self._response_synthesizer.generate_voice_text(role_llm, display_text)

    async def _run_theless_synthesis_with_timeout(
        self,
        chat_ctx: Any,
        role_llm: Any = None,
    ) -> tuple[str, str]:
        return await self._response_synthesizer.run_theless_synthesis_with_timeout(
            chat_ctx,
            role_llm=role_llm,
        )

    async def _run_theless_synthesis(self, chat_ctx: Any, role_llm: Any = None) -> str:
        return await self._response_synthesizer.run_theless_synthesis(
            chat_ctx,
            role_llm=role_llm,
        )

    def _record_synthesis_metrics(
        self,
        *,
        synthesis_status: str,
        fallback_used: bool,
        fallback_source: str,
        tool_name: str,
        mode: str,
    ) -> None:
        self._response_synthesizer.record_synthesis_metrics(
            synthesis_status=synthesis_status,
            fallback_used=fallback_used,
            fallback_source=fallback_source,
            tool_name=tool_name,
            mode=mode,
        )

    def _get_tool_response_template(
        self,
        tool_name: str,
        structured_data: Optional[Dict[str, Any]],
        mode: str = "normal",
    ) -> Optional[str]:
        return self._tool_response_builder.get_tool_response_template(
            tool_name,
            structured_data,
            mode=mode,
        )

    async def _build_agent_response(
        self,
        role_llm: Any,
        raw_output: str,
        *,
        mode: str = "normal",
        tool_invocations: Optional[List[ToolInvocation]] = None,
        structured_data: Optional[Dict[str, Any]] = None,
    ) -> AgentResponse:
        return await self._response_synthesizer.build_agent_response(
            role_llm,
            raw_output,
            mode=mode,
            tool_invocations=tool_invocations,
            structured_data=structured_data,
        )

    def _safe_json_dump(self, data: Any) -> str:
        return self._tool_response_builder.safe_json_dump(data)

    async def _synthesize_tool_response(
        self,
        role_llm: Any,
        user_message: str,
        tool_name: str,
        tool_output: Any,
        tool_invocation: ToolInvocation,
        mode: str = "normal",
    ) -> AgentResponse:
        return await self._tool_response_builder.synthesize_tool_response(
            role_llm=role_llm,
            user_message=user_message,
            tool_name=tool_name,
            tool_output=tool_output,
            tool_invocation=tool_invocation,
            mode=mode,
        )

    async def _build_direct_tool_response(
        self,
        role_llm: Any,
        tool_output: Any,
        tool_invocation: ToolInvocation,
    ) -> AgentResponse:
        return await self._tool_response_builder.build_direct_tool_response(
            role_llm=role_llm,
            tool_output=tool_output,
            tool_invocation=tool_invocation,
        )

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
        return await self._task_runtime_service.handle_task_request(
            user_text,
            user_id,
            tool_context=tool_context,
        )

    async def _try_handle_report_export_task(
        self,
        *,
        user_text: str,
        user_id: str,
        tool_context: Any = None,
    ) -> str | None:
        return await self._task_runtime_service.try_handle_report_export_task(
            user_text=user_text,
            user_id=user_id,
            tool_context=tool_context,
        )

    @staticmethod
    def _compose_report_markdown(query: str, summary: str, sources: list[Any]) -> str:
        return TaskRuntimeService.compose_report_markdown(query, summary, sources)

    async def _ensure_task_worker(self, user_id: str) -> None:
        await self._task_runtime_service.ensure_task_worker(user_id)

    async def shutdown(self) -> None:
        await self._task_runtime_service.shutdown()

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
