import logging
import asyncio
import os
# Heavy component imports are deferred to the functions that actually need them.
# Phase 1 build_phase1_runtime() does NOT import these at all.

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# PHASE 1: Minimal Voice Runtime
# ──────────────────────────────────────────────────────────────────────────────

class Phase1Runtime:
    """
    Holds only the components needed for Phase 1:
    raw LLM + STT + TTS + VAD.

    No memory, no tools, no orchestrator, no SmartLLM.
    """
    def __init__(
        self,
        llm,
        stt,
        tts,
        vad,
        stt_provider_name: str = "unknown",
        degraded_mode: bool = False,
        stt_failover_reason: str | None = None,
    ):
        self.llm = llm
        self.stt = stt
        self.tts = tts
        self.vad = vad
        self.stt_provider_name = stt_provider_name
        self.degraded_mode = degraded_mode
        self.stt_failover_reason = stt_failover_reason


async def build_phase1_runtime(phase_label: int | None = None) -> "Phase1Runtime":
    """
    Phase 1 bootstrap: creates ONLY the voice providers.

    Does NOT touch GlobalAgentContainer, HybridMemoryManager, ToolManager,
    AgentOrchestrator, PlanningEngine, TaskStore, SmartLLM, or ContextBuilder.

    Call this from _handle_worker_session() instead of build_worker_runtime_from_global().
    """
    phase_text = str(phase_label) if phase_label is not None else "unknown"
    logger.info("🔥 VOICE_PROVIDER_RUNTIME_INIT phase=%s", phase_text)

    from config.settings import settings
    from providers.factory import ProviderFactory
    from providers.sttprovider import build_stt_with_failover
    from livekit.plugins import silero
    from core.runtime.global_agent import GlobalAgentContainer

    logger.info(f"🧠 [Phase 1] Initializing LLM: {settings.llm_provider} / {settings.llm_model}")
    llm = ProviderFactory.get_llm(settings.llm_provider, settings.llm_model)

    stt_auto_failover = str(os.getenv("STT_AUTO_FAILOVER_ENABLED", "true")).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    stt_failover_target = str(os.getenv("STT_FAILOVER_TARGET", "groq")).strip().lower() or "groq"
    stt_probe_timeout_s = max(0.5, float(os.getenv("STT_HEALTH_PROBE_TIMEOUT_S", "2.0")))
    logger.info(
        "🎤 [Phase 1] Initializing STT requested=%s auto_failover=%s failover_target=%s probe_timeout_s=%.2f",
        settings.stt_provider,
        stt_auto_failover,
        stt_failover_target,
        stt_probe_timeout_s,
    )
    stt, active_stt_provider, degraded_mode, failover_reason = build_stt_with_failover(
        provider_name=settings.stt_provider,
        language=settings.stt_language,
        model=settings.stt_model,
        failover_enabled=stt_auto_failover,
        failover_target=stt_failover_target,
        probe_timeout_s=stt_probe_timeout_s,
    )
    logger.info(
        "🎤 STT_PROVIDER_ACTIVE requested=%s active=%s degraded_mode=%s reason=%s",
        settings.stt_provider,
        active_stt_provider,
        degraded_mode,
        failover_reason or "none",
    )

    logger.info(f"🔊 [Phase 1] Initializing TTS: {settings.tts_provider}")
    tts = ProviderFactory.get_tts(
        settings.tts_provider,
        settings.tts_voice,
        settings.tts_model,
        supervisor=GlobalAgentContainer.provider_supervisor,
    )

    logger.info("🔇 [Phase 1] Initializing VAD (Silero)...")
    vad = silero.VAD.load(
        min_silence_duration=0.4,
        min_speech_duration=0.05,
        activation_threshold=0.5,
        sample_rate=8000,
    )

    logger.info("✅ VOICE_PROVIDER_RUNTIME_READY phase=%s", phase_text)
    return Phase1Runtime(
        llm=llm,
        stt=stt,
        tts=tts,
        vad=vad,
        stt_provider_name=active_stt_provider,
        degraded_mode=degraded_mode,
        stt_failover_reason=failover_reason,
    )


# ──────────────────────────────────────────────────────────────────────────────
# PHASE 2+: Full Runtime (GlobalAgentContainer-backed)
# ──────────────────────────────────────────────────────────────────────────────

# ── Regression Guard ─────────────────────────────────────────────────────────
# Tracks how many times build_worker_runtime_from_global() has been called
# within this process. Each call beyond 1 is a duplication fault.
_RUNTIME_BUILD_CALL_COUNT: int = 0
_MAX_RUNTIME_BUILDS_PER_PROCESS: int = 1  # LiveKit may spawn N slots per process

class WorkerRuntime:
    """
    Holds the runtime components for a single worker process.
    These are initialized once per worker process startup.
    """
    def __init__(
        self,
        memory_manager,
        tools,
        evaluation_engine,
        smart_llm, 
        ingestor,
        stt=None,
        tts=None,
        vad=None
    ):
        self.memory_manager = memory_manager
        self.tools = tools
        self.evaluation_engine = evaluation_engine
        self.smart_llm = smart_llm
        self.ingestor = ingestor
        self.stt = stt
        self.tts = tts
        self.vad = vad

async def build_worker_runtime_from_global() -> WorkerRuntime:
    """
    Builds a WorkerRuntime by consuming the already-initialized singletons from
    GlobalAgentContainer. This avoids re-initializing heavy components (Memory,
    LLM, Tools, SmartLLM) that were already loaded during the warm phase.

    Only STT, TTS, and VAD are initialized here since GlobalAgentContainer
    does not manage audio providers.
    """
    global _RUNTIME_BUILD_CALL_COUNT
    _RUNTIME_BUILD_CALL_COUNT += 1

    # LiveKit pre-warms N parallel worker slots per process — each slot calling this
    # once is acceptable. If a single slot calls it more than once, that's a fault.
    # We log a warning for any call beyond the first to surface it clearly.
    if _RUNTIME_BUILD_CALL_COUNT > _MAX_RUNTIME_BUILDS_PER_PROCESS:
        logger.warning(
            f"⚠️ REGRESSION GUARD: build_worker_runtime_from_global() called "
            f"{_RUNTIME_BUILD_CALL_COUNT}× in this process "
            f"(expected ≤{_MAX_RUNTIME_BUILDS_PER_PROCESS} per job). "
            "Possible duplicate worker slot init — investigate entrypoint registration."
        )

    logger.info(
        f"🔧 Building worker runtime from global singletons "
        f"[call #{_RUNTIME_BUILD_CALL_COUNT}, no double-boot]..."
    )

    from core.runtime.global_agent import GlobalAgentContainer

    # Ensure global container is initialized (should already be, but guard anyway)
    if not GlobalAgentContainer._initialized:
        logger.warning("⚠️ GlobalAgentContainer not initialized — initializing now...")
        await GlobalAgentContainer.initialize()

    # Reuse already-warmed heavy singletons
    memory_manager = GlobalAgentContainer.get_memory()
    ingestor = GlobalAgentContainer.memory_ingestor
    tools = GlobalAgentContainer.get_tools()
    base_llm = GlobalAgentContainer.get_llm()

    logger.info(f"🔧 TOOL COUNT: {len(tools)} tools available (not injected in Phase 1)")

    # Phase 1: SmartLLM constructed but context_builder=None.
    # agent.py uses base_llm directly and does NOT call SmartLLM yet.
    # SmartLLM is kept here so future phases can layer on top without
    # changing the bootstrap interface.
    worker_smart_llm = SmartLLM(
        base_llm=base_llm,
        context_builder=None   # Phase 1: no custom context builder
    )

    # Only initialize audio providers (lightweight, not in GlobalAgentContainer)
    logger.info("🎤 Initializing STT & TTS Providers...")
    from config.settings import settings
    stt_provider = ProviderFactory.get_stt(
        settings.stt_provider,
        settings.stt_language,
        settings.stt_model,
        supervisor=GlobalAgentContainer.provider_supervisor,
    )
    tts_provider = ProviderFactory.get_tts(
        settings.tts_provider,
        settings.tts_voice,
        settings.tts_model,
        supervisor=GlobalAgentContainer.provider_supervisor,
    )

    logger.info("🔇 Initializing VAD (Silero)...")
    from livekit.plugins import silero
    vad_provider = silero.VAD.load(
        min_silence_duration=0.4,    # 400ms silence → end of speech
        min_speech_duration=0.05,    # 50ms minimum speech chunk
        activation_threshold=0.5,    # default confidence threshold
        sample_rate=8000,            # 8kHz model — 2x lighter than 16kHz
    )

    # Initialize Evaluation Engine (stateless, cheap)
    logger.info("🔍 Initializing Evaluation Engine...")
    try:
        evaluation_engine = EvaluationEngine()
    except Exception as e:
        logger.error(f"Failed to initialize evaluation engine: {e}")
        raise e

    logger.info("✅ Worker runtime built from global singletons successfully")

    return WorkerRuntime(
        memory_manager=memory_manager,
        tools=tools,
        evaluation_engine=evaluation_engine,
        smart_llm=worker_smart_llm,
        ingestor=ingestor,
        stt=stt_provider,
        tts=tts_provider,
        vad=vad_provider,
    )


async def bootstrap_worker_runtime() -> WorkerRuntime:
    """
    DEPRECATED: Use build_worker_runtime_from_global() instead.

    This function re-initializes all heavy components from scratch, causing
    double-bootstrap memory pressure when called after GlobalAgentContainer
    has already been warmed. Kept for backward compatibility only.
    """
    logger.warning(
        "⚠️ bootstrap_worker_runtime() is deprecated and causes double-bootstrap. "
        "Use build_worker_runtime_from_global() instead."
    )
    return await build_worker_runtime_from_global()
