
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
from core.tasks.planning_engine import PlanningEngine
from core.tasks.task_store import TaskStore
from core.action.constants import ActionStateConfig
from core.action.state_store import ActionStateStore
from core.context.context_guard import ContextGuard
from core.memory.hybrid_memory_manager import HybridMemoryManager
from core.memory.preference_manager import PreferenceManager
from core.orchestrator.agent_router import AgentRouter
from core.orchestrator.chat_mixin import ChatResponseMixin
from core.orchestrator.context_assembler import ContextAssembler
from core.orchestrator.fast_path_router import FastPathRouter, DirectToolIntent
from core.orchestrator.interaction_manager import InteractionManager
from core.orchestrator.media_resolver import MediaResolver
from core.orchestrator.orchestration_flow import OrchestrationFlow
from core.orchestrator.conversation_tape import ConversationTape
from core.orchestrator.orchestrator_constants import (
    CONVERSATIONAL_MEMORY_TRIGGERS,
    DEEP_RESEARCH_KEYWORDS,
    MEDIA_EXCLUDE_PATTERNS,
    MEDIA_PATTERNS,
    RECALL_EXCLUDED_TOOLS,
    RECALL_EXCLUSION_PATTERNS,
    REPORT_EXPORT_KEYWORDS,
    REPORT_EXPORT_PATTERNS,
    TASK_COMPLETION_PATTERNS,
    TOOL_ERROR_HINT_PATTERN,
    VOICE_ACTION_SECOND_TOKEN_ALLOWLIST,
    VOICE_CONTINUATION_MARKERS,
    VOICE_SHORT_COMMAND_ALLOWLIST,
    VOICE_TRANSCRIPTION_NORMALIZATIONS,
)
from core.orchestrator.pronoun_rewriter import PronounRewriter
from core.orchestrator.research_handler import ResearchHandler
from core.orchestrator.media_handler import MediaHandler
from core.orchestrator.memory_context_service import MemoryContextService
from core.orchestrator.scheduling_handler import SchedulingHandler
from core.orchestrator.session_lifecycle import SessionLifecycle
from core.orchestrator.response_synthesizer import ResponseSynthesizer
from core.orchestrator.tool_executor import ToolExecutor
from core.orchestrator.tool_response_builder import ToolResponseBuilder
from core.orchestrator.task_runtime_service import TaskRuntimeService
from core.orchestrator.voice_coordinator import VoiceCoordinator
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
        }
        self._conversation_history: List[Dict[str, Any]] = []
        self._router_llm_adapter = _RouterLLMAdapter(agent)
        self._conversation_tape = ConversationTape(
            event_cap=max(40, int(os.getenv("CONVERSATION_TAPE_EVENT_CAP", "240"))),
            llm_client=self._router_llm_adapter,
            enable_llm_backfill=str(
                os.getenv("CONVERSATION_TAPE_LLM_BACKFILL", "true")
            ).strip().lower() in {"1", "true", "yes", "on"},
        )
        self._session_continuity_injected: bool = False
        self._current_user_id: Optional[str] = None
        self._current_session_id: Optional[str] = None
        self._attached_session_identity: Optional[str] = None
        self._action_state_enabled = self._is_truthy_env(
            os.getenv("ACTION_STATE_ENABLED", "true")
        )
        self._last_action_followup_enabled = self._is_truthy_env(
            os.getenv("LAST_ACTION_FOLLOWUP_ENABLED", "true")
        )
        self._action_state_carryover_enabled = (
            self._is_truthy_env(os.getenv("ACTION_STATE_CARRYOVER_ENABLED", "true"))
            and self._action_state_enabled
        )
        ttl_raw = os.getenv("LAST_ACTION_TTL_SECONDS", "1800")
        max_turns_raw = os.getenv("LAST_ACTION_MAX_TURNS", "5")
        try:
            last_action_ttl_seconds = max(1, int(str(ttl_raw).strip()))
        except Exception:
            last_action_ttl_seconds = 1800
        try:
            last_action_max_turns = max(1, int(str(max_turns_raw).strip()))
        except Exception:
            last_action_max_turns = 5
        self._action_state_store = (
            ActionStateStore(
                ActionStateConfig(
                    last_action_ttl_seconds=last_action_ttl_seconds,
                    last_action_max_turns=last_action_max_turns,
                )
            )
            if self._action_state_enabled
            else None
        )
        logger.info(
            "action_state_initialized enabled=%s followup_enabled=%s carryover_enabled=%s ttl_s=%s max_turns=%s",
            self._action_state_enabled,
            self._last_action_followup_enabled,
            self._action_state_carryover_enabled,
            last_action_ttl_seconds,
            last_action_max_turns,
        )

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
            owner=self,
        )
        self._media_handler = MediaHandler(owner=self)
        self._scheduling_handler = SchedulingHandler(owner=self)
        self._session_lifecycle = SessionLifecycle(owner=self)
        self._context_assembler = ContextAssembler(owner=self)
        # Load personality from settings for use in fast-path handlers
        from config.settings import settings as _settings
        self._personality = getattr(_settings, "agent_personality", "professional")

        self._interaction_manager = InteractionManager(owner=self)
        self._voice_coordinator = VoiceCoordinator(owner=self)
        self._enable_research_llm_planner = self._is_truthy_env(
            os.getenv("ENABLE_RESEARCH_LLM_PLANNER", "false")
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
        self._router = AgentRouter(self._router_llm_adapter)
        self._agent_registry = get_agent_registry()
        self._handoff_manager = get_handoff_manager(self._agent_registry)
        self._outcome_logger: Any = None
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
        self._session_lifecycle.set_session_bootstrap_context(session_id, payload)

    def clear_session_bootstrap_context(self, session_id: str) -> None:
        self._session_lifecycle.clear_session_bootstrap_context(session_id)

    def _augment_message_with_session_bootstrap(self, message: str, session_id: str) -> str:
        return self._session_lifecycle.augment_message_with_session_bootstrap(message, session_id)

    def _extract_user_message_segment(self, augmented: str) -> Optional[str]:
        return self._session_lifecycle.extract_user_message_segment(augmented)

    CONVERSATIONAL_MEMORY_TRIGGERS = CONVERSATIONAL_MEMORY_TRIGGERS
    RECALL_EXCLUSION_PATTERNS = RECALL_EXCLUSION_PATTERNS
    RECALL_EXCLUDED_TOOLS = RECALL_EXCLUDED_TOOLS
    TASK_COMPLETION_PATTERNS = TASK_COMPLETION_PATTERNS
    _TOOL_ERROR_HINT_PATTERN = TOOL_ERROR_HINT_PATTERN
    _REPORT_EXPORT_PATTERNS = REPORT_EXPORT_PATTERNS
    _REPORT_EXPORT_KEYWORDS = REPORT_EXPORT_KEYWORDS
    _DEEP_RESEARCH_KEYWORDS = DEEP_RESEARCH_KEYWORDS
    MEDIA_PATTERNS = MEDIA_PATTERNS
    MEDIA_EXCLUDE_PATTERNS = MEDIA_EXCLUDE_PATTERNS
    _VOICE_TRANSCRIPTION_NORMALIZATIONS = VOICE_TRANSCRIPTION_NORMALIZATIONS
    _VOICE_SHORT_COMMAND_ALLOWLIST = VOICE_SHORT_COMMAND_ALLOWLIST
    _VOICE_CONTINUATION_MARKERS = VOICE_CONTINUATION_MARKERS
    _VOICE_ACTION_SECOND_TOKEN_ALLOWLIST = VOICE_ACTION_SECOND_TOKEN_ALLOWLIST

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
        try:
            from core.runtime.global_agent import GlobalAgentContainer

            monitor = GlobalAgentContainer.get_monitor()
            if monitor is not None:
                total_ms = max(0, int(plan_ms) + int(search_ms) + int(synth_ms))
                monitor.log_route("research", float(total_ms), trace_id=trace_id)
                monitor.log_tool("web_search", float(search_ms), trace_id=trace_id)
        except Exception:
            # Observability must never break orchestration flow.
            pass

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
        return await self._interaction_manager.handle_identity_fast_path(
            message=message,
            user_id=user_id,
            origin=origin,
        )

    def _match_small_talk_fast_path(self, message: str) -> Optional[str]:
        return self._interaction_manager.match_small_talk_fast_path(message)

    def _extract_subject_from_text(self, raw_text: str) -> str:
        return self._research_handler._extract_subject_from_text(raw_text)

    def _session_key_for_context(self, tool_context: Any = None) -> str:
        return self._session_lifecycle.resolve_session_queue_key(tool_context)

    def _set_last_action_for_context(
        self,
        *,
        action: Dict[str, Any],
        tool_context: Any = None,
    ) -> bool:
        if not self._action_state_enabled:
            return False
        store = self._action_state_store
        if store is None:
            return False
        session_key = self._session_key_for_context(tool_context)
        store.set_last_action(session_key, action)
        return True

    def _get_last_action_for_context(self, tool_context: Any = None) -> Optional[Dict[str, Any]]:
        if not self._action_state_enabled:
            return None
        store = self._action_state_store
        if store is None:
            return None
        session_key = self._session_key_for_context(tool_context)
        return store.get_last_action(session_key)

    def _current_action_state_turn(self, tool_context: Any = None) -> int:
        if not self._action_state_enabled:
            return 0
        store = self._action_state_store
        if store is None:
            return 0
        session_key = self._session_key_for_context(tool_context)
        return store.current_turn(session_key)

    def _extract_summary_sentence(self, summary: str) -> str:
        return self._research_handler._extract_summary_sentence(summary)

    def _store_research_context(self, query: str, summary: str, *, tool_context: Any = None) -> None:
        session_key = self._session_key_for_context(tool_context)
        self._research_handler.store_research_context(query=query, summary=summary, session_key=session_key)
        if active := self._research_handler.get_active_research_context(session_key):
            self._last_research_contexts[session_key] = dict(active)

    def _get_active_research_context(self, tool_context: Any = None) -> Optional[Dict[str, Any]]:
        session_key = self._session_key_for_context(tool_context)
        context = self._research_handler.get_active_research_context(session_key)
        if context:
            self._last_research_contexts[session_key] = dict(context)
            return context
        if not (context := self._last_research_contexts.get(session_key)):
            return None
        if float(context.get("expires_at") or 0.0) <= time.time():
            self._last_research_contexts.pop(session_key, None)
            return None
        return context

    def _resolve_research_subject_from_context(self, tool_context: Any = None) -> str:
        session_key = self._session_key_for_context(tool_context)
        payload = self._session_bootstrap_contexts.get(str(session_key or "").strip()) or {}
        tape_history = self._session_lifecycle.get_tape_history(
            session_id=session_key,
            limit=max(40, int(os.getenv("PRONOUN_RESOLUTION_HISTORY_EVENTS", "120"))),
        )
        return self._research_handler.resolve_research_subject_from_context(
            research_context=self._get_active_research_context(tool_context),
            conversation_history=tape_history or self._conversation_history,
            bootstrap_payload=payload,
        )

    def _resolve_active_subject_for_fast_path(self) -> str:
        return self._research_handler.resolve_active_subject_for_fast_path(
            self._get_active_research_context(),
            self._resolve_research_subject_from_context(),
        )

    def rewrite_research_query_for_context(
        self,
        query: str,
        *,
        tool_context: Any = None,
    ) -> tuple[str, bool, bool]:
        session_key = self._session_key_for_context(tool_context)
        history = self._session_lifecycle.get_tape_history(
            session_id=session_key,
            limit=max(40, int(os.getenv("PRONOUN_RESOLUTION_HISTORY_EVENTS", "120"))),
        )
        return self._pronoun_rewriter.rewrite(
            query,
            conversation_history=history or self._conversation_history,
            research_context=self._get_active_research_context(tool_context),
            tool_context=tool_context,
        )

    def _rewrite_pronoun_followup_pre_router(
        self,
        raw_query: str,
        *,
        tool_context: Any = None,
    ) -> tuple[str, bool, bool]:
        query = re.sub(r"\s+", " ", str(raw_query or "")).strip()
        if not query:
            return "", False, False
        if not self._pronoun_rewriter.should_check_rewrite(query):
            return query, False, False
        session_key = self._session_key_for_context(tool_context)
        history = self._session_lifecycle.get_tape_history(
            session_id=session_key,
            limit=max(40, int(os.getenv("PRONOUN_RESOLUTION_HISTORY_EVENTS", "120"))),
        )
        return self._pronoun_rewriter.rewrite(
            query,
            conversation_history=history or self._conversation_history,
            research_context=self._get_active_research_context(tool_context),
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
        return self._context_assembler.build_context_slice(
            target_agent=target_agent,
            message=message,
            user_id=user_id,
            tool_context=tool_context,
            host_profile=host_profile,
        )

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
        self._session_lifecycle.update_turn_identity(user_id=user_id, session_id=session_id)

    def _start_new_turn(self, user_message: str, turn_id: Optional[str] = None) -> str:
        return self._session_lifecycle.start_new_turn(user_message, turn_id=turn_id)

    def _append_conversation_history(
        self,
        role: str,
        content: str,
        source: str = "history",
        route: str = "",
    ) -> None:
        self._session_lifecycle.append_conversation_history(
            role=role,
            content=content,
            source=source,
            route=route,
        )

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
        return ResearchHandler.is_multi_step_task_request(message_lower)

    def _is_report_export_request(self, message: str) -> bool:
        return self._research_handler.is_report_export_request(
            message,
            report_export_keywords=self._REPORT_EXPORT_KEYWORDS,
            report_export_patterns=self._REPORT_EXPORT_PATTERNS,
        )

    def _should_use_deep_research_voice(self, query: str) -> bool:
        return self._voice_coordinator.should_use_deep_research_voice(
            query,
            deep_keywords=self._DEEP_RESEARCH_KEYWORDS,
        )

    @staticmethod
    def _slugify_topic(text: str) -> str:
        return ResearchHandler.slugify_topic(text)

    def _build_report_output_path(self, query: str) -> str:
        return self._research_handler.build_report_output_path(query)

    @staticmethod
    def _extract_report_focus_query(user_text: str) -> str:
        return ResearchHandler.extract_report_focus_query(user_text)

    def inject_session_continuity_summary(self, summary: str) -> bool:
        return self._session_lifecycle.inject_session_continuity_summary(summary)

    def _filter_chat_history_for_fallthrough(self, history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return self._context_assembler.filter_chat_history_for_fallthrough(history)

    def _context_message_tokens(self, messages: List[Any]) -> int:
        return self._context_assembler.context_message_tokens(messages)

    @staticmethod
    def _chat_ctx_messages(chat_ctx: Any) -> List[Any]:
        return ContextAssembler.chat_ctx_messages(chat_ctx)

    @staticmethod
    def _message_content_to_text(message: Any) -> str:
        return ContextAssembler.message_content_to_text(message)

    @staticmethod
    def _message_role_value(message: Any) -> str:
        return ContextAssembler.message_role_value(message)

    def _is_voice_continuation_fragment(
        self,
        *,
        routing_text: str,
        origin: str,
        chat_ctx_messages: List[Any],
    ) -> bool:
        state = self._voice_utterance_state(
            routing_text=routing_text,
            origin=origin,
            chat_ctx_messages=chat_ctx_messages,
        )
        return state in {"fragment", "continuation"}

    def _voice_utterance_state(
        self,
        *,
        routing_text: str,
        origin: str,
        chat_ctx_messages: List[Any],
    ) -> str:
        return self._voice_coordinator.classify_utterance_state(
            routing_text=routing_text,
            origin=origin,
            chat_ctx_messages=chat_ctx_messages,
            short_command_allowlist=self._VOICE_SHORT_COMMAND_ALLOWLIST,
            continuation_markers=self._VOICE_CONTINUATION_MARKERS,
            action_second_token_allowlist=self._VOICE_ACTION_SECOND_TOKEN_ALLOWLIST,
        )

    def _get_conversation_tape_history(
        self,
        *,
        session_id: str,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        return self._session_lifecycle.get_tape_history(session_id=session_id, limit=limit)

    def _tool_name(self, tool: Any) -> str:
        return self._context_assembler.tool_name(tool)

    async def _maybe_await(self, value: Any) -> Any:
        if inspect.isawaitable(value):
            return await value
        return value

    def _resolve_phase3_chat_tools(self) -> List[Any]:
        return self._context_assembler.resolve_phase3_chat_tools(
            enable_chat_tools=self.enable_chat_tools,
            architecture_phase=int(getattr(settings, "architecture_phase", 1)),
        )

    def _parse_legacy_function_call(self, text: str) -> Optional[tuple[str, Dict[str, Any]]]:
        return self._voice_coordinator.parse_legacy_function_call(text)

    def _is_tool_call_generation_error(self, err: Exception) -> bool:
        return self._voice_coordinator.is_tool_call_generation_error(err)

    def _normalize_tool_invocation(
        self,
        tool_name: str,
        args: Dict[str, Any],
    ) -> tuple[str, Dict[str, Any]]:
        return self._voice_coordinator.normalize_tool_invocation(tool_name, args)

    def _strip_legacy_function_markup(self, text: str) -> str:
        return self._voice_coordinator.strip_legacy_function_markup(text)

    def _sanitize_response(self, text: str) -> str:
        return self._voice_coordinator.sanitize_response(text)

    def _sanitize_research_voice_for_tts(
        self,
        voice: str,
        display: str,
        *,
        voice_mode: str = "brief",
    ) -> tuple[str, str]:
        return self._voice_coordinator.sanitize_research_voice_for_tts(
            voice,
            display,
            voice_mode=voice_mode,
        )

    def _parse_multi_app(self, app_phrase: str) -> List[str]:
        return self._voice_coordinator.parse_multi_app(app_phrase)

    # ─── Inlined from legacy.py ────────────────────────────────────────────────

    def set_session(self, session: Any):
        self._session_lifecycle.set_session(session)

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
        self._voice_coordinator.on_transcription_received(transcription)

    async def process_chat_message(self, text: str):
        await self._voice_coordinator.process_chat_message(text)

    def _on_data_received(self, *args):
        self._voice_coordinator.on_data_received(*args)

    @staticmethod
    def parse_client_config(participant: Any) -> Dict[str, Any]:
        return VoiceCoordinator.parse_client_config(participant)

    # ─── End inlined legacy methods ────────────────────────────────────────────

    def _retrieve_memories(
        self,
        user_input: str,
        k: int = 5,
        user_id: str | None = None,
        session_id: str | None = None,
        origin: str = "chat",
    ) -> List[Dict[str, Any]]:
        return self._context_assembler.retrieve_memories(
            user_input,
            k=k,
            user_id=user_id,
            session_id=session_id,
            origin=origin,
        )

    def _format_memory_context(self, memories: List[Dict[str, Any]]) -> str:
        return self._context_assembler.format_memory_context(memories)

    def _retrieve_memory_context(
        self,
        user_input: str,
        k: int = 5,
        user_id: str | None = None,
        session_id: str | None = None,
        origin: str = "chat",
    ) -> str:
        return self._context_assembler.retrieve_memory_context(
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
        return await self._context_assembler.run_sync_with_timeout(
            func,
            *args,
            timeout_s=timeout_s,
        )

    def _is_tool_focused_query(self, message: str) -> bool:
        return self._context_assembler.is_tool_focused_query(message)

    def _is_memory_relevant(self, text: str) -> bool:
        return self._context_assembler.is_memory_relevant(text)

    def _is_recall_exclusion_intent(self, text: str) -> bool:
        return self._context_assembler.is_recall_exclusion_intent(text)

    def _should_skip_memory(
        self,
        text: str,
        origin: str,
        routing_mode_type: str,
    ) -> tuple[bool, str]:
        return self._context_assembler.should_skip_memory(
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
        return await self._context_assembler.retrieve_memory_context_async(
            user_input,
            origin=origin,
            routing_mode_type=routing_mode_type,
            user_id=user_id,
            session_id=session_id,
        )

    def _is_malformed_short_request(self, message: str) -> bool:
        return self._interaction_manager.is_malformed_short_request(message)

    def _is_conversational_query(self, message: str) -> bool:
        return self._interaction_manager.is_conversational_query(message)

    def _is_name_query(self, message: str) -> bool:
        return self._interaction_manager.is_name_query(message)

    def _is_creator_query(self, message: str) -> bool:
        return self._interaction_manager.is_creator_query(message)

    def _is_identity_dominant_query(self, message: str) -> bool:
        return self._interaction_manager.is_identity_dominant_query(message)

    def _strip_identity_preamble_if_needed(self, user_query: str, raw_text: str) -> str:
        return self._interaction_manager.strip_identity_preamble_if_needed(user_query, raw_text)

    async def _apply_action_state_carryover(self, message: str) -> str:
        return await self._interaction_manager.apply_action_state_carryover(message)

    def _resolve_last_action_followup(
        self,
        message: str,
        *,
        tool_context: Any = None,
    ) -> Optional[AgentResponse]:
        return self._interaction_manager.resolve_last_action_followup(
            message=message,
            tool_context=tool_context,
        )

    def _is_user_name_recall_query(self, message: str) -> bool:
        return self._interaction_manager.is_user_name_recall_query(message)

    @staticmethod
    def _extract_name_from_memory_messages(messages: List[Any]) -> Optional[str]:
        return InteractionManager.extract_name_from_memory_messages(messages)

    async def _lookup_profile_name_from_memory(
        self,
        *,
        user_id: str,
        session_id: str | None,
        origin: str = "chat",
    ) -> Optional[str]:
        return await self._interaction_manager.lookup_profile_name_from_memory(
            user_id=user_id,
            session_id=session_id,
            origin=origin,
        )

    def _summarize_task_start(self, user_text: str, steps: List[Any]) -> str:
        return ResearchHandler.summarize_task_start(user_text, steps)

    def _queue_preference_update(self, user_id: str, key: str, value: Any, source: str) -> None:
        self._interaction_manager.queue_preference_update(user_id, key, value, source)

    def _queue_preference_extraction(self, user_text: str, user_id: str) -> None:
        self._interaction_manager.queue_preference_extraction(user_text, user_id)

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
        return ResearchHandler.compose_report_markdown(query, summary, sources)

    async def _ensure_task_worker(self, user_id: str) -> None:
        await self._task_runtime_service.ensure_task_worker(user_id)

    async def shutdown(self) -> None:
        await self._task_runtime_service.shutdown()

    def _resolve_session_queue_key(self, tool_context: Any = None) -> str:
        return self._session_lifecycle.resolve_session_queue_key(tool_context)

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
            async def _write_memory() -> None:
                write_ok = await store_turn(
                    user_msg=user_text,
                    assistant_msg=response_text,
                    metadata={"source": "conversation", "role": "chat"},
                    user_id=user_id,
                    session_id=session_id,
                )
                if write_ok:
                    logger.info(
                        "memory_write_confirmed user_id=%s session_id=%s origin=%s",
                        user_id,
                        session_id or "none",
                        origin or "unknown",
                    )
                else:
                    logger.warning(
                        "memory_write_failed user_id=%s session_id=%s origin=%s",
                        user_id,
                        session_id or "none",
                        origin or "unknown",
                    )

            asyncio.create_task(_write_memory())
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
