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
    _task_workers: dict[str, Any] = {}
    _sentinel: Any = None        # BehavioralSentinel
    provider_supervisor: Any = None
    _host_capability_profile: Any = None
    _memory_warmup_task: Optional[asyncio.Task[Any]] = None
    _app_cache_preload_task: Optional[asyncio.Task[Any]] = None
    _message_bus: Any = None
    _progress_stream: Any = None
    _task_persistence: Any = None
    _subagent_circuit_breaker: Any = None

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
        from core.tasks.task_persistence import TaskPersistence
        from core.memory.hybrid_memory_manager import HybridMemoryManager
        from core.memory.memory_ingestor import MemoryIngestor
        from core.memory.preference_manager import PreferenceManager
        from core.tasks.task_tools import get_task_tools
        from core.registry.tool_registry import get_registry
        from core.system.host_capability_profile import collect_host_capability_profile
        from core.messaging.message_bus import MessageBus
        from core.messaging.progress_stream import ProgressStream
        from core.agents.subagent_circuit_breaker import SubagentCircuitBreaker

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
        cls._task_persistence = TaskPersistence(store=cls._task_store)
        cls._message_bus = MessageBus(
            max_queue_depth=getattr(settings, "max_message_bus_queue_depth_global", 1000),
        )
        cls._subagent_circuit_breaker = SubagentCircuitBreaker(
            failure_threshold=3,
            half_open_cooldown_s=60.0,
        )

        async def _emit_progress_to_log(payload: dict[str, Any]) -> None:
            logger.info(
                "progress_stream_event phase=%s agent=%s status=%s percent=%s trace_id=%s task_id=%s",
                payload.get("phase"),
                payload.get("agent"),
                payload.get("status"),
                payload.get("percent"),
                payload.get("trace_id"),
                payload.get("task_id"),
            )
            orchestrator = cls._orchestrator
            room = getattr(orchestrator, "room", None) if orchestrator is not None else None
            if room is not None:
                try:
                    from core.communication import publish_chat_event

                    await publish_chat_event(
                        room,
                        {
                            "type": "task_progress",
                            "status": payload.get("status"),
                            "percent": payload.get("percent"),
                            "summary": payload.get("summary"),
                            "task_id": payload.get("task_id"),
                            "trace_id": payload.get("trace_id"),
                            "timestamp": payload.get("timestamp"),
                        },
                    )
                except Exception as progress_publish_err:
                    logger.debug("progress_event_room_publish_failed error=%s", progress_publish_err)

        cls._progress_stream = ProgressStream(
            bus=cls._message_bus,
            emitter=_emit_progress_to_log,
            max_events_per_sec_per_session=getattr(
                settings, "max_progress_events_per_sec_per_session", 10
            ),
        )
        await cls._progress_stream.start()
        try:
            recoverable = await cls._task_persistence.load_recoverable_tasks()
            logger.info("task_recovery_scan recoverable_count=%s", len(recoverable))
        except Exception as recovery_err:
            logger.warning("task_recovery_scan_failed error=%s", recovery_err)
        
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
            create_calendar_event, list_calendar_events, delete_calendar_event
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
        setattr(cls._orchestrator, "_message_bus", cls._message_bus)
        setattr(cls._orchestrator, "_task_persistence", cls._task_persistence)
        setattr(cls._orchestrator, "_subagent_circuit_breaker", cls._subagent_circuit_breaker)
        setattr(cls._orchestrator, "_progress_stream", cls._progress_stream)

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
    async def shutdown_background_tasks(cls) -> None:
        """Stop long-lived background tasks owned by the global container."""
        if cls._progress_stream is not None:
            try:
                await cls._progress_stream.stop()
            except Exception as e:
                logger.warning(f"⚠️ Failed to stop progress stream: {e}")
            finally:
                cls._progress_stream = None

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
