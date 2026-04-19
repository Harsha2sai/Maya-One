import logging
import asyncio
import os
from typing import Optional, List, Any

# Deferred Imports for Circular Dependency Avoidance
# We use Any for type hints to avoid importing classes at module level
from config.settings import settings
from core.observability.trace_context import current_trace_id, set_trace_context, start_trace

logger = logging.getLogger(__name__)

class GlobalAgentContainer:
    """
    Singleton container for heavy agent components.
    Ensures these are loaded ONCE per worker process, not per session.
    """

    _initialized: bool = False
    _memory: Any = None          # HybridMemoryManager
    memory_ingestor: Any = None        # MemoryIngestor
    _preference_manager: Any = None
    _task_store: Any = None      # SQLiteTaskStore
    _tools: List[Any] = []
    _llm: Any = None             # Base LLM
    _smart_llm: Any = None       # SmartLLM (with tools)
    _orchestrator: Any = None    # ConsoleOrchestrator (created once)
    _hook_registry: Any = None   # HookRegistry
    _session_store: Any = None   # Memdir SessionStore
    _user_preferences_store: Any = None  # Memdir UserPreferences
    _task_workers: dict[str, Any] = {}
    _sentinel: Any = None        # BehavioralSentinel
    provider_supervisor: Any = None
    _host_capability_profile: Any = None
    _memory_warmup_task: Optional[asyncio.Task[Any]] = None
    _app_cache_preload_task: Optional[asyncio.Task[Any]] = None
    _msg_hub: Any = None         # MayaMsgHub (P28 infrastructure)
    _worktree_manager: Any = None  # P29 worktree isolation manager
    _subagent_manager: Any = None  # P29 subagent lifecycle manager
    _team_coordinator: Any = None  # P30 team mode coordinator
    _ralph_executor: Any = None    # P30 $ralph executor
    _buddy: Any = None             # P33 Buddy companion
    _project_mode: Any = None      # P35 project mode orchestrator
    _feature_flags: Any = None     # P36 feature flag system
    _dream_cycle: Any = None       # P36 dream memory consolidator
    _outcome_logger: Any = None    # P37 task outcome logger
    _training_exporter: Any = None # P37 training set exporter
    _evaluator: Any = None         # P37 benchmark evaluator
    _command_registry: Any = None  # P34 slash command registry
    _plugin_loader: Any = None     # P34 plugin loader
    _monitor: Any = None         # MayaMonitor (P28 observability bridge)
    _a2a_server: Any = None      # MayaA2AServer foundation stub (P28)
    _agentscope_memory: Any = None  # MayaAgentScopeMemory parallel store (P28)
    _ide_session_manager: Any = None  # P12.1 IDE session lifecycle manager
    _ide_file_service: Any = None     # P12.1 IDE workspace-scoped file service
    _ide_action_guard: Any = None     # P12.1 IDE action guard
    _ide_state_bus: Any = None        # P12.1 IDE event/state bus
    _terminal_manager: Any = None     # P12.3 terminal manager (PTY + websocket)

    @classmethod
    async def initialize(cls):
        """
        Async initialization of heavy components.
        Should be called once at worker startup.
        """
        if cls._initialized:
            return

        logger.info("🔥 Booting GLOBAL AGENT (one-time initialization)...")
        start_trace(session_id="global_boot", user_id="system")
        runtime_mode = str(os.getenv("MAYA_RUNTIME_MODE", "worker") or "worker").strip().lower()

        # Ensure strict tool-schema compatibility in every runtime path
        # (worker already patches, but console/API paths also need this).
        from utils.schema_fixer import apply_schema_patch
        apply_schema_patch(settings.llm_provider)

        # Local imports prevent circular dependencies during worker boot.
        from core.tools.tool_manager import ToolManager
        from providers.factory import ProviderFactory
        from core.tasks.task_store import SQLiteTaskStore
        from core.hooks.registry import HookRegistry
        from core.memory.hybrid_memory_manager import HybridMemoryManager
        from core.memory.memdir import SessionStore, UserPreferences
        from core.memory.memory_ingestor import MemoryIngestor
        from core.memory.preference_manager import PreferenceManager
        from core.tasks.task_tools import get_task_tools
        from core.registry.tool_registry import get_registry
        from core.system.host_capability_profile import collect_host_capability_profile
        from core.memory.agentscope_store import MayaAgentScopeMemory
        from core.observability import MayaMonitor
        from core.a2a import MayaA2AServer
        from core.ide import (
            ActionGuard,
            IDEFileService,
            IDESessionManager,
            IDEStateBus,
            TerminalManager,
        )
        from core.agents.subagent import (
            SubAgentManager as RuntimeSubAgentManager,
            WorktreeManager as RuntimeWorktreeManager,
        )
        from core.agents.team import TeamCoordinator
        from core.agents.coding import RalphExecutor
        from core.buddy import BuddyCompanion
        from core.project import ProjectModeOrchestrator
        from core.features import FeatureFlagSystem
        from core.commands import CommandRegistry
        from core.plugins import PluginLoader
        from core.rl import OutcomeLogger, TrainingExporter, MayaEvaluator

        cls._host_capability_profile = collect_host_capability_profile(runtime_mode=runtime_mode)
        logger.info("host_capability_collected profile=%s", cls._host_capability_profile.to_dict())

        # 1. Initialize Memory (Singleton)
        # VectorStore lazy loading is handled internally
        cls._memory = HybridMemoryManager()
        try:
            logger.info("vector_store_eager_init: forcing model load before fork")
            _ = cls._memory.retriever.vector_store.embedding_model
            logger.info("vector_store_eager_init_complete")
        except Exception as eager_err:
            logger.warning(f"⚠️ vector_store_eager_init_failed: {eager_err}")
        try:
            cls._memory_warmup_task = asyncio.create_task(
                asyncio.to_thread(cls._memory.retriever.warm_up)
            )
            logger.info("🧠 Retriever warm-up scheduled in background")
        except Exception as e:
            logger.warning(f"⚠️ Retriever warm-up scheduling failed during global boot: {e}")
        
        # 1.1 Initialize Ingestor (Singleton)
        cls.memory_ingestor = MemoryIngestor(memory_manager=cls._memory)
        cls._preference_manager = PreferenceManager()

        
        # 2. Initialize Task Store (Singleton)
        cls._task_store = SQLiteTaskStore("./dev_maya_one.db")
        cls._hook_registry = HookRegistry()
        memdir_root = str(os.getenv("MAYA_MEMDIR_HOME", "")).strip() or None
        cls._session_store = SessionStore(base_dir=memdir_root)
        cls._user_preferences_store = UserPreferences(base_dir=memdir_root)

        # P28: Initialize MsgHub (infrastructure only — not yet used)
        from core.messaging import MayaMsgHub
        cls._msg_hub = MayaMsgHub()
        logger.info("📨 MayaMsgHub initialized (P28 infrastructure)")
        cls._worktree_manager = RuntimeWorktreeManager()
        cls._subagent_manager = RuntimeSubAgentManager(
            msg_hub=cls._msg_hub,
            worktree_manager=cls._worktree_manager,
        )
        logger.info("🤖 SubAgentManager initialized (P29)")
        cls._team_coordinator = TeamCoordinator(
            subagent_manager=cls._subagent_manager,
            msg_hub=cls._msg_hub,
        )
        cls._ralph_executor = RalphExecutor(
            subagent_manager=cls._subagent_manager,
        )
        logger.info("🤝 TeamCoordinator + RalphExecutor initialized (P30)")
        cls._buddy = BuddyCompanion(
            subagent_manager=cls._subagent_manager,
            db_path=cls._task_store.db_path,
        )
        logger.info("BuddyCompanion initialized (P33)")
        cls._command_registry = CommandRegistry()
        cls._feature_flags = FeatureFlagSystem()
        logger.info("FeatureFlagSystem initialized (P36)")
        cls._outcome_logger = OutcomeLogger()
        cls._training_exporter = TrainingExporter(cls._outcome_logger)
        logger.info("OutcomeLogger + TrainingExporter initialized (P37)")
        cls._project_mode = ProjectModeOrchestrator(
            subagent_manager=cls._subagent_manager,
            buddy=cls._buddy,
            command_registry=cls._command_registry,
        )
        logger.info("ProjectModeOrchestrator initialized (P35)")
        cls._register_builtin_commands()
        plugin_dir = str(os.getenv("MAYA_PLUGIN_DIR", "plugins") or "plugins").strip()
        cls._plugin_loader = PluginLoader(plugin_dir=plugin_dir)
        loaded_plugins = cls._plugin_loader.load_all(cls._command_registry)
        logger.info("P34 plugin_loader initialized loaded=%s", loaded_plugins)
        cls._monitor = MayaMonitor()
        logger.info("📈 MayaMonitor initialized (P28 observability)")
        cls._a2a_server = MayaA2AServer(agent_name="maya")
        logger.info("🔌 MayaA2AServer initialized available=%s", cls._a2a_server.available)
        cls._agentscope_memory = MayaAgentScopeMemory(db_path=cls._task_store.db_path)
        logger.info("🧠 MayaAgentScopeMemory initialized (parallel to HybridMemoryManager)")
        cls._ide_session_manager = IDESessionManager(max_concurrent=5)
        cls._ide_file_service = IDEFileService(cls._ide_session_manager)
        cls._ide_action_guard = ActionGuard()
        cls._ide_state_bus = IDEStateBus()
        cls._terminal_manager = TerminalManager()
        await cls._ide_session_manager.start_cleanup()
        cls._terminal_manager.on_audit(cls._forward_terminal_audit_event)
        await cls._terminal_manager.start()
        logger.info("🧰 IDE runtime initialized (P12.1 foundation)")
        
        # 3. Initialize Base LLM (Singleton connection/config)
        provider_name = str(settings.llm_provider or "").strip().lower()
        provider_slot_prefix = {
            "groq": "GROQ",
            "gemini": "GEMINI",
            "openai": "OPENAI",
            "anthropic": "ANTHROPIC",
            "deepseek": "DEEPSEEK",
            "mistral": "MISTRAL",
            "perplexity": "PERPLEXITY",
            "together": "TOGETHER",
            "nvidia": "NVIDIA",
            "qwen": "QWEN",
        }

        def _configured_slots(prefix: str) -> list[int]:
            slots: set[int] = set()
            if os.getenv(f"{prefix}_API_KEY", "").strip():
                slots.add(1)

            max_slot = 1
            slot_count_env = os.getenv(f"{prefix}_SLOT_COUNT", "").strip()
            if slot_count_env.isdigit():
                max_slot = max(1, int(slot_count_env))

            for env_name, env_value in os.environ.items():
                if not env_name.startswith(f"{prefix}_API_KEY_"):
                    continue
                raw_slot = env_name.removeprefix(f"{prefix}_API_KEY_")
                if not raw_slot.isdigit():
                    continue
                slot = int(raw_slot)
                max_slot = max(max_slot, slot)
                if str(env_value or "").strip():
                    slots.add(slot)

            return [slot for slot in range(1, max_slot + 1) if slot in slots]

        prefix = provider_slot_prefix.get(provider_name)
        preferred_slot = 1
        if prefix:
            raw_active = os.getenv(f"{prefix}_ACTIVE_KEY_SLOT", "1").strip()
            if raw_active.isdigit():
                preferred_slot = max(1, int(raw_active))

        llm_kwargs = {}
        if prefix:
            llm_kwargs["key_slot"] = preferred_slot
        cls._llm = ProviderFactory.get_llm(settings.llm_provider, settings.llm_model, **llm_kwargs)

        fallback_llm = None
        if prefix:
            for slot in _configured_slots(prefix):
                if slot == preferred_slot:
                    continue
                try:
                    fallback_llm = ProviderFactory.get_llm(
                        settings.llm_provider,
                        settings.llm_model,
                        key_slot=slot,
                    )
                    logger.info(
                        f"✅ Global SmartLLM fallback configured with {provider_name} key slot {slot}"
                    )
                    break
                except Exception as e:
                    logger.warning(
                        f"⚠️ Failed to initialize {provider_name} slot-{slot} fallback: {e}"
                    )

        if fallback_llm is None and provider_name != "openai" and os.getenv("OPENAI_API_KEY", "").strip():
            fallback_model = os.getenv("OPENAI_FALLBACK_MODEL", "gpt-4o-mini")
            try:
                fallback_llm = ProviderFactory.get_llm("openai", fallback_model)
                logger.info(f"✅ Global SmartLLM fallback configured with OpenAI ({fallback_model})")
            except Exception as e:
                logger.warning(f"⚠️ Failed to initialize OpenAI fallback: {e}")
        
        # 4. Initialize Tools (Heavy MCP + Local)
        from tools.system.pc_control import (
            run_shell_command,
            file_write,
            open_app,
            close_app,
            set_volume,
            take_screenshot,
            preload_installed_apps_cache,
        )
        from tools import (
            web_search, get_weather, get_current_datetime, get_date, get_time,
            send_email, set_alarm, list_alarms, delete_alarm,
            set_reminder, list_reminders, delete_reminder,
            create_note, list_notes, read_note, delete_note,
            create_calendar_event, list_calendar_events, delete_calendar_event
        )
        from tools.system.filesystem import (
            list_directory, search_files, file_exists, file_metadata,
            file_hash, count_file_lines, read_file, read_file_chunk,
            fetch_webpage, move_file, copy_file, download_file,
            create_pdf, create_docx,
        )

        # P31: Tier 1 + Tier 2 tools
        from core.tools.file_ops import file_read, file_write as p31_file_write, file_edit, file_glob, file_grep
        from core.tools.execution import bash
        from core.tools.agent_tools import spawn_subagent, check_agent_result, send_agent_message

        local_tools = get_task_tools() + [
            run_shell_command, file_write, open_app, close_app, set_volume, take_screenshot,
        list_directory, search_files,
        file_exists, file_metadata, file_hash, count_file_lines,
        read_file, read_file_chunk, fetch_webpage,
        move_file, copy_file, download_file,
        create_pdf, create_docx,
 get_weather, get_current_datetime, get_date, get_time,
            send_email, set_alarm, list_alarms, delete_alarm,
            set_reminder, list_reminders, delete_reminder,
            create_note, list_notes, read_note, delete_note,
            create_calendar_event, list_calendar_events, delete_calendar_event,
            # P31 Tier 1 — file ops + shell
            file_read, p31_file_write, file_edit, file_glob, file_grep, bash,
            # P31 Tier 2 — agent coordination
            spawn_subagent, check_agent_result, send_agent_message,
        ]

        async def _preload_app_cache() -> None:
            try:
                indexed = await asyncio.to_thread(preload_installed_apps_cache, force_refresh=False)
                logger.info(f"🗂️ Preloaded installed app cache ({indexed} entries)")
            except Exception as e:
                logger.warning(f"⚠️ Failed to preload installed app cache: {e}")

        if runtime_mode != "console":
            try:
                cls._app_cache_preload_task = asyncio.create_task(_preload_app_cache())
                logger.info("🗂️ Installed app cache preload scheduled in background")
            except Exception as e:
                logger.warning(f"⚠️ Failed to schedule installed app cache preload: {e}")
        
        # Load and register all tools
        cls._tools = await ToolManager.load_all_tools(local_tools)

        # 5. Initialize Shared Orchestrator (Unified Runtime)
        from core.orchestrator.agent_orchestrator import AgentOrchestrator
        from core.llm.smart_llm import SmartLLM
        # Use Headless Mocks for ctx/room dependency
        from core.runtime.headless import HeadlessJobContext

        # Create SmartLLM wrapper with warmed components
        # Context builder must preserve orchestrator-built context for console mode.
        async def console_context_builder(user_msg, chat_ctx=None):
            from livekit.agents.llm import ChatMessage
            if chat_ctx is not None:
                messages = chat_ctx.messages() if callable(chat_ctx.messages) else chat_ctx.messages
                if messages:
                    return (list(messages), cls._tools)
            # Fallback when no context exists yet.
            return ([ChatMessage(role="user", content=[user_msg])], cls._tools)

        cls._smart_llm = SmartLLM(
            base_llm=cls._llm,
            fallback_llm=fallback_llm,
            context_builder=console_context_builder, 
            session_id="global_session" 
        )

        # Mock Agent object to hold smart_llm property expected by AgentOrchestrator
        class GlobalAgentWrapper:
            def __init__(self, smart_llm):
                self.smart_llm = smart_llm
        
        agent_wrapper = GlobalAgentWrapper(cls._smart_llm)
        headless_ctx = HeadlessJobContext()

        cls._orchestrator = AgentOrchestrator(
            ctx=headless_ctx,
            agent=agent_wrapper,
            session=None,  # No audio session in console
            memory_manager=cls._memory,
            ingestor=cls.memory_ingestor,
            preference_manager=cls._preference_manager,
            enable_chat_tools=max(1, int(getattr(settings, "architecture_phase", 1))) >= 3,
            enable_task_pipeline=max(1, int(getattr(settings, "architecture_phase", 1))) >= 4,
        )
        cls._evaluator = MayaEvaluator(cls._orchestrator)
        cls._orchestrator._outcome_logger = cls._outcome_logger
        logger.info("MayaEvaluator initialized and outcome logger attached (P37)")
        from core.memory.dream import DreamCycle
        cls._dream_cycle = DreamCycle(
            memory_manager=cls._memory,
            llm=cls._smart_llm,
        )
        logger.info("DreamCycle initialized (P36)")

        cls._initialized = True
        logger.info(f"✅ Global agent ready with {len(cls._tools)} tools")

        # Start behavioral sentinel after initialization
        if runtime_mode != "console":
            try:
                from core.observability.behavioral_sentinel import BehavioralSentinel

                cls._sentinel = BehavioralSentinel(orchestrator=cls._orchestrator)
                asyncio.create_task(cls._sentinel.start())
                logger.info("🛡️ Behavioral sentinel started")
            except Exception as e:
                logger.warning(f"⚠️ Failed to start behavioral sentinel: {e}")

    @classmethod
    def get_components(cls):
        """Return the shared components for session construction."""
        if not cls._initialized:
             logger.warning("⚠️ GlobalAgentContainer accessed before initialization! Auto-initializing (Sync Blocking)")
             # Fallback attempt (might fail if loop running)
             pass
             
        return cls._memory, cls._task_store, cls._tools, cls._llm

    @classmethod
    def get_memory(cls) -> Any:
        return cls._memory

    @classmethod
    def get_tools(cls) -> List[Any]:
        return cls._tools

    @classmethod
    def get_llm(cls) -> Any:
        return cls._llm

    @classmethod
    def get_orchestrator(cls) -> Any:
        """Return the shared AgentOrchestrator instance."""
        return cls._orchestrator

    @classmethod
    def get_hook_registry(cls) -> Any:
        """Return the shared HookRegistry instance."""
        return cls._hook_registry

    @classmethod
    def get_session_store(cls) -> Any:
        """Return the shared memdir SessionStore instance."""
        return cls._session_store

    @classmethod
    def get_user_preferences_store(cls) -> Any:
        """Return the shared memdir UserPreferences store instance."""
        return cls._user_preferences_store
    
    @classmethod
    def get_msg_hub(cls) -> Any:
        """Return the shared MayaMsgHub instance (P28+)."""
        return cls._msg_hub

    @classmethod
    def get_subagent_manager(cls) -> Any:
        """Return the shared P29 SubAgentManager instance."""
        return cls._subagent_manager

    @classmethod
    def get_team_coordinator(cls) -> Any:
        """Return the shared P30 TeamCoordinator instance."""
        return cls._team_coordinator

    @classmethod
    def get_ralph_executor(cls) -> Any:
        """Return the shared P30 RalphExecutor instance."""
        return cls._ralph_executor

    @classmethod
    def get_buddy(cls) -> Any:
        """Return the shared P33 BuddyCompanion instance."""
        return cls._buddy

    @classmethod
    def get_command_registry(cls) -> Any:
        """Return the shared P34 CommandRegistry instance."""
        return cls._command_registry

    @classmethod
    def get_project_mode(cls) -> Any:
        """Return the shared P35 ProjectModeOrchestrator instance."""
        return cls._project_mode

    @classmethod
    def get_feature_flags(cls) -> Any:
        """Return the shared P36 FeatureFlagSystem instance."""
        return cls._feature_flags

    @classmethod
    def get_dream_cycle(cls) -> Any:
        """Return the shared P36 DreamCycle instance."""
        return cls._dream_cycle

    @classmethod
    def get_outcome_logger(cls) -> Any:
        """Return the shared P37 OutcomeLogger instance."""
        return cls._outcome_logger

    @classmethod
    def get_training_exporter(cls) -> Any:
        """Return the shared P37 TrainingExporter instance."""
        return cls._training_exporter

    @classmethod
    def get_evaluator(cls) -> Any:
        """Return the shared P37 MayaEvaluator instance."""
        return cls._evaluator

    @classmethod
    def get_plugin_loader(cls) -> Any:
        """Return the shared P34 PluginLoader instance."""
        return cls._plugin_loader

    @classmethod
    async def dispatch_command(cls, raw: str, context: Optional[dict] = None) -> Optional[str]:
        """Dispatch slash commands through the shared command registry."""
        if cls._command_registry is None:
            return None
        payload = cls._build_command_context()
        payload.update(context or {})
        payload["command_registry"] = cls._command_registry
        return await cls._command_registry.dispatch(raw, payload)

    @classmethod
    def _build_command_context(cls) -> dict:
        from core.governance.gate import ExecutionGate

        return {
            "subagent_manager": cls._subagent_manager,
            "buddy": cls._buddy,
            "execution_gate": ExecutionGate,
            "command_registry": cls._command_registry,
            "memory": cls._memory,
            "project_mode": cls._project_mode,
            "feature_flags": cls._feature_flags,
            "dream_cycle": cls._dream_cycle,
            "outcome_logger": cls._outcome_logger,
            "training_exporter": cls._training_exporter,
            "evaluator": cls._evaluator,
        }

    @classmethod
    def _register_builtin_commands(cls) -> None:
        from core.commands import SlashCommand
        from core.commands.handlers.agent import handle_agents, handle_kill, handle_spawn
        from core.commands.handlers.buddy import handle_buddy, handle_evolve, handle_xp
        from core.commands.handlers.dream import handle_dream
        from core.commands.handlers.flags import handle_flag
        from core.commands.handlers.memory import handle_forget, handle_recall, handle_remember
        from core.commands.handlers.mode import handle_lock, handle_mode, handle_unlock
        from core.commands.handlers.project import handle_project
        from core.commands.handlers.rl import handle_rl
        from core.commands.handlers.system import handle_help, handle_reset, handle_status

        if cls._command_registry is None:
            return

        builtins = [
            SlashCommand("spawn", "Spawn a specialist subagent", "/spawn <type> <task>", handle_spawn),
            SlashCommand("agents", "List active agents", "/agents", handle_agents),
            SlashCommand("kill", "Terminate an agent", "/kill <agent_id>", handle_kill),
            SlashCommand("buddy", "Show Buddy status", "/buddy", handle_buddy),
            SlashCommand("xp", "Show Buddy XP details", "/xp", handle_xp),
            SlashCommand("evolve", "Award Buddy XP event", "/evolve [event]", handle_evolve),
            SlashCommand("mode", "Get or set permission mode", "/mode [mode_name]", handle_mode),
            SlashCommand("lock", "Lock tool execution", "/lock", handle_lock),
            SlashCommand("unlock", "Unlock to default mode", "/unlock", handle_unlock),
            SlashCommand("remember", "Store lightweight command memory", "/remember <key> <value>", handle_remember),
            SlashCommand("forget", "Forget lightweight command memory", "/forget <key>", handle_forget),
            SlashCommand("recall", "Recall lightweight command memory", "/recall <key>", handle_recall),
            SlashCommand("project", "Manage project mode workflow", "/project <subcommand>", handle_project),
            SlashCommand("flag", "Manage runtime feature flags", "/flag [enable|disable|list|reset] [FLAG]", handle_flag),
            SlashCommand("dream", "Consolidate memory for the session", "/dream [--preview]", handle_dream),
            SlashCommand("rl", "Inspect/export RL outcomes", "/rl [stats|eval|export|rate]", handle_rl),
            SlashCommand("help", "List available commands", "/help", handle_help),
            SlashCommand("status", "Show system status", "/status", handle_status),
            SlashCommand("reset", "Reset command-facing state", "/reset", handle_reset),
        ]
        for cmd in builtins:
            cls._command_registry.register(cmd)

    @classmethod
    def get_monitor(cls) -> Any:
        """Return the shared MayaMonitor instance (P28+)."""
        return cls._monitor

    @classmethod
    def get_a2a_server(cls) -> Any:
        """Return the shared MayaA2AServer foundation instance (P28+)."""
        return cls._a2a_server

    @classmethod
    def get_agentscope_memory(cls) -> Any:
        """Return the shared MayaAgentScopeMemory parallel store (P28+)."""
        return cls._agentscope_memory

    @classmethod
    def get_ide_session_manager(cls) -> Any:
        """Return the shared IDE session manager (P12.1)."""
        return cls._ide_session_manager

    @classmethod
    def get_ide_file_service(cls) -> Any:
        """Return the shared IDE file service (P12.1)."""
        return cls._ide_file_service

    @classmethod
    def get_ide_action_guard(cls) -> Any:
        """Return the shared IDE action guard (P12.1)."""
        return cls._ide_action_guard

    @classmethod
    def get_ide_state_bus(cls) -> Any:
        """Return the shared IDE state bus (P12.1)."""
        return cls._ide_state_bus

    @classmethod
    def get_terminal_manager(cls) -> Any:
        """Return the shared terminal manager (P12.3)."""
        return cls._terminal_manager

    @classmethod
    def get_host_capability_profile(cls, refresh: bool = False):
        from core.system.host_capability_profile import (
            collect_host_capability_profile,
            refresh_host_capability_profile,
        )

        runtime_mode = str(os.getenv("MAYA_RUNTIME_MODE", "worker") or "worker").strip().lower()
        if cls._host_capability_profile is None:
            cls._host_capability_profile = collect_host_capability_profile(runtime_mode=runtime_mode)
            logger.info("host_capability_collected profile=%s", cls._host_capability_profile.to_dict())
        elif refresh:
            cls._host_capability_profile = refresh_host_capability_profile(cls._host_capability_profile)
            logger.info("host_capability_refreshed profile=%s", cls._host_capability_profile.to_dict())
        return cls._host_capability_profile

    @classmethod
    async def handle_user_message(cls, user_text: str):
        """
        Unified Gateway for user messages (Console/API).
        Routes to the shared AgentOrchestrator.
        """
        if not cls._orchestrator:
             logger.error("❌ Orchestrator not initialized!")
             return "System Error: Orchestrator not ready."
        set_trace_context(
            trace_id=current_trace_id(),
            session_id="global_session",
            user_id="console_user",
        )
             
        # Call the shared orchestrator directly
        # The Orchestrator handles intent routing, tools, and RAG
        return await cls._orchestrator.handle_message(user_text, user_id="console_user")

    @classmethod
    async def start_task_worker(cls, user_id: str):
        """Start the background TaskWorker for the given user."""
        existing = cls._task_workers.get(user_id)
        if existing and getattr(existing, "is_running", False):
            logger.info(f"👷 TaskWorker already running for {user_id}.")
            return

        if not cls._initialized:
            await cls.initialize()

        logger.info(f"👷 Starting TaskWorker for {user_id}...")
        from core.tasks.task_worker import TaskWorker
        
        # We need to pass smart_llm for the registry
        worker = TaskWorker(
            user_id=user_id,
            memory_manager=cls._memory,
            smart_llm=cls._smart_llm
        )
        await worker.start()
        cls._task_workers[user_id] = worker

    @classmethod
    async def stop_task_workers(cls):
        """Stop all background TaskWorkers started via the container."""
        workers = list(cls._task_workers.values())
        cls._task_workers.clear()
        for worker in workers:
            try:
                await worker.stop()
            except Exception as e:
                logger.warning(f"⚠️ Failed stopping TaskWorker: {e}")

    @classmethod
    async def _forward_terminal_audit_event(cls, event: Any) -> None:
        """Forward terminal audit events into IDE state bus."""
        if cls._ide_state_bus is None:
            return

        event_map = {
            "open": "terminal_opened",
            "input": "terminal_input",
            "output": "terminal_output",
            "resize": "terminal_resized",
            "close": "terminal_closed",
            "error": "terminal_error",
            "reconnect": "terminal_reconnected",
            "timeout": "terminal_timeout",
        }
        mapped_type = event_map.get(str(getattr(event, "event_type", "")).strip(), "terminal_event")
        details = dict(getattr(event, "details", {}) or {})
        await cls._ide_state_bus.emit(
            mapped_type,
            {
                "session_id": getattr(event, "session_id", None),
                "agent_id": "terminal",
                "status": str(getattr(event, "event_type", "") or ""),
                "payload": details,
                "timestamp": float(getattr(event, "timestamp", 0.0) or 0.0),
            },
        )

    @classmethod
    async def shutdown_background_tasks(cls) -> None:
        """Stop long-lived background tasks owned by the global container."""
        if cls._sentinel is not None:
            try:
                await cls._sentinel.stop()
            except Exception as e:
                logger.warning(f"⚠️ Failed to stop behavioral sentinel: {e}")
            finally:
                cls._sentinel = None

        for task_attr in ("_app_cache_preload_task", "_memory_warmup_task"):
            task = getattr(cls, task_attr, None)
            if task is None:
                continue
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                except Exception as e:
                    logger.warning(f"⚠️ Failed to stop {task_attr}: {e}")
            setattr(cls, task_attr, None)

        if cls._a2a_server is not None:
            try:
                await cls._a2a_server.stop()
            except Exception as e:
                logger.warning(f"⚠️ Failed to stop MayaA2AServer: {e}")
            finally:
                cls._a2a_server = None

        if cls._ide_session_manager is not None:
            try:
                await cls._ide_session_manager.stop_cleanup()
            except Exception as e:
                logger.warning(f"⚠️ Failed to stop IDE session cleanup loop: {e}")

        if cls._terminal_manager is not None:
            try:
                await cls._terminal_manager.stop()
            except Exception as e:
                logger.warning(f"⚠️ Failed to stop terminal manager: {e}")
            finally:
                cls._terminal_manager = None
