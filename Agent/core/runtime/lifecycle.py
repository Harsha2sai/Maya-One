
import os
import sys
import logging
import asyncio
import subprocess
import time
import resource
from enum import Enum

# Use absolute imports for core components
# Note: These should be careful not to trigger port-binding side effects
from core.runtime.startup_checks import run_startup_checks
from core.runtime.global_agent import GlobalAgentContainer
from core.utils.intent_utils import normalize_intent
from config.settings import settings
from core.observability.trace_context import (
    current_trace_id,
    enable_trace_logging,
    set_trace_context,
    start_trace,
)

logger = logging.getLogger(__name__)


_PROVIDER_HOST_MAP = {
    "groq": "api.groq.com",
    "elevenlabs": "api.elevenlabs.io",
    "deepgram": "api.deepgram.com",
    "cartesia": "api.cartesia.ai",
    "openai": "api.openai.com",
    "azure": "azure",
}


def _provider_host(provider_name: str) -> str:
    normalized = str(provider_name or "").strip().lower()
    return _PROVIDER_HOST_MAP.get(normalized, normalized or "unknown")


def _register_inference_runners() -> None:
    """
    Register inference runners needed by LiveKit worker-side inference process.

    For livekit-agents 1.4.x, turn detector runners are registered as a side effect
    of importing the language modules. This must happen before AgentServer starts,
    otherwise job processes will log `no inference executor`.
    """
    try:
        # Side-effect imports: register _InferenceRunner entries.
        from livekit.plugins.turn_detector import english as _td_english  # noqa: F401
        from livekit.plugins.turn_detector import multilingual as _td_multilingual  # noqa: F401
        from livekit.agents.inference_runner import _InferenceRunner

        registered = sorted(_InferenceRunner.registered_runners.keys())
        logger.info(
            "✅ inference_runners_registered count=%s methods=%s",
            len(registered),
            registered,
        )
    except Exception as e:
        logger.warning(
            "⚠️ Unable to pre-register inference runners for turn detector: %s",
            e,
            exc_info=True,
        )


class MayaRuntimeMode(Enum):
    WORKER = "worker"
    CONSOLE = "console"

class RuntimeLifecycleManager:
    """
    Single source of truth for the Maya-One boot process.
    Controls the sequence of port cleanup, resource warming, and mode execution.
    """
    def __init__(self, mode: MayaRuntimeMode):
        self.mode = mode
        self.architecture_phase = max(1, int(getattr(settings, "architecture_phase", 1)))
        self.runtime = None
        self._background_tasks: list[asyncio.Task] = []
        self.memory_ingestor = None  # To track for shutdown
        from core.providers.provider_supervisor import ProviderSupervisor

        self.provider_supervisor = ProviderSupervisor(
            failure_threshold=settings.circuit_breaker_threshold,
            recovery_timeout_s=settings.circuit_breaker_recovery_s,
            success_threshold=settings.circuit_breaker_success_threshold,
        )

    async def boot(self, entrypoint_fnc=None):
        """Execute the full startup pipeline in strict order."""
        enable_trace_logging()
        mode_str = normalize_intent(self.mode)
        os.environ["MAYA_RUNTIME_MODE"] = mode_str
        start_trace(session_id=f"lifecycle:{mode_str}", user_id="system")
        print(f"🧱 Maya Runtime Lifecycle: Booting as {mode_str.upper()}...")
        logger.info(f"🧭 Architecture phase selected: Phase {self.architecture_phase}")

        # Phase 6.1: prevent HF network retry stalls during embedding model load.
        self._configure_hf_offline_mode()

        # 1. Preflight (Cleanup and Checks)
        await self._preflight()
        
        # 2. Global Agent Boot (Resources)
        await self._boot_global_agent()
        
        # 3. Mode Specific Execution
        await self._boot_mode_specific(entrypoint_fnc)

    async def shutdown(self):
        """Graceful shutdown of all services."""
        logger.info("🛑 Shutdown started")

        # Cancel background tasks
        for task in self._background_tasks:
            task.cancel()

        if self._background_tasks:
            await asyncio.gather(*self._background_tasks, return_exceptions=True)

        # Stop services
        if self.memory_ingestor is None:
            # Phase 2/3 currently initializes ingestor in the global container.
            # Pull it here so shutdown always attempts a graceful stop.
            self.memory_ingestor = GlobalAgentContainer.memory_ingestor

        # Stop orchestrator-managed task workers first (phase 4+).
        try:
            orchestrator = GlobalAgentContainer.get_orchestrator()
            if orchestrator and hasattr(orchestrator, "shutdown"):
                await orchestrator.shutdown()
        except Exception as e:
            logger.warning(f"⚠️ Failed to shutdown orchestrator workers: {e}")
        try:
            if hasattr(GlobalAgentContainer, "stop_task_workers"):
                await GlobalAgentContainer.stop_task_workers()
        except Exception as e:
            logger.warning(f"⚠️ Failed to shutdown global task workers: {e}")
        try:
            if hasattr(GlobalAgentContainer, "shutdown_background_tasks"):
                await GlobalAgentContainer.shutdown_background_tasks()
        except Exception as e:
            logger.warning(f"⚠️ Failed to shutdown global background tasks: {e}")

        if self.memory_ingestor is not None:
            try:
                await self.memory_ingestor.stop()
            except Exception as e:
                logger.warning(f"⚠️ MemoryIngestor stop error (non-fatal): {e}")
        
        if self.provider_supervisor:
            await self.provider_supervisor.stop()

        logger.info("🏁 Shutdown completed")
        
    def _start_background_task(self, coro):
        task = asyncio.create_task(coro)
        self._background_tasks.append(task)
        return task

    def _configure_hf_offline_mode(self) -> None:
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        os.environ["HF_DATASETS_OFFLINE"] = "1"
        logger.info(
            "🧠 HuggingFace offline mode enabled (TRANSFORMERS_OFFLINE=%s HF_DATASETS_OFFLINE=%s)",
            os.environ.get("TRANSFORMERS_OFFLINE"),
            os.environ.get("HF_DATASETS_OFFLINE"),
        )

    async def _preflight(self):
        """Absolute first steps: Port clearance and validation."""
        print("🔍 Step 1: Preflight & Port Cleanup...")
        try:
            if self.mode == MayaRuntimeMode.WORKER:
                # Worker mode owns the token server and worker ports.
                if os.path.exists("scripts/cleanup_ports.sh"):
                    subprocess.run(["bash", "scripts/cleanup_ports.sh"], capture_output=True)
                else:
                    # Fallback if scripts dir not available (unlikely in prod)
                    subprocess.run(["fuser", "-k", "5050/tcp"], capture_output=True)
                    subprocess.run(["fuser", "-k", "8081/tcp"], capture_output=True)
                    subprocess.run(["fuser", "-k", "8082/tcp"], capture_output=True)

                await asyncio.sleep(1.5)
                run_startup_checks(require_runtime_ports=True)
            else:
                # Console mode is in-process and must not tear down shared ports.
                await asyncio.sleep(0.05)
                run_startup_checks(require_runtime_ports=False)
            print("✅ Preflight checks passed.")
        except Exception as e:
            logger.error(f"❌ Preflight failed: {e}")
            sys.exit(1)

    async def _boot_global_agent(self):
        """Warm up singleton resources based on the selected architecture phase."""
        print("🧠 Step 2: Warming Global Resources...")
        try:
            if self.architecture_phase <= 1:
                logger.info(f"🔥 PHASE 1 MODE: Pure LiveKit ({self.mode.name}) — skipping GlobalAgentContainer")
                print(f"✅ Phase 1: {self.mode.name} mode — heavy singletons skipped.")
                return

            if self.mode == MayaRuntimeMode.CONSOLE:
                should_eager_warm_console = str(
                    os.getenv("MAYA_CONSOLE_EAGER_WARM", "0")
                ).strip().lower() in {"1", "true", "yes"}
                if not should_eager_warm_console:
                    logger.info(
                        "ℹ️ Console mode using deferred GlobalAgentContainer warm-up "
                        "(set MAYA_CONSOLE_EAGER_WARM=1 for eager boot)"
                    )
                    print(
                        f"✅ Phase {self.architecture_phase}: console deferred global warm-up "
                        "(on-demand)."
                    )
                    return

            # Phase 2+: pre-warm the shared single-brain container once.
            logger.info(f"🧠 PHASE {self.architecture_phase}: warming GlobalAgentContainer")
            await GlobalAgentContainer.initialize()
            self.memory_ingestor = GlobalAgentContainer.memory_ingestor
            print(f"✅ Phase {self.architecture_phase}: global resources ready.")
            logger.info("✅ GlobalAgentContainer warmed successfully")

            try:
                supervisor = self.provider_supervisor
                provider_candidates = []

                smart_llm = getattr(GlobalAgentContainer, "_smart_llm", None)
                if smart_llm is not None:
                    base_llm = getattr(smart_llm, "base_llm", None)
                    fallback_llm = getattr(smart_llm, "fallback_llm", None)
                    if base_llm is not None:
                        provider_candidates.append(base_llm)
                    if fallback_llm is not None:
                        provider_candidates.append(fallback_llm)
                else:
                    base_llm = GlobalAgentContainer.get_llm()
                    if base_llm is not None:
                        provider_candidates.append(base_llm)

                seen_provider_keys: set[str] = set()
                for idx, provider in enumerate(provider_candidates, start=1):
                    provider_key = str(getattr(provider, "provider", "") or "").strip().lower()
                    if not provider_key:
                        provider_key = f"llm_provider_{idx}"
                    provider_host = _provider_host(provider_key)
                    if provider_host in seen_provider_keys:
                        continue
                    seen_provider_keys.add(provider_host)
                    supervisor.register_provider(provider_host, provider)

                configured_tts_host = _provider_host(settings.tts_provider)
                if configured_tts_host not in seen_provider_keys:
                    seen_provider_keys.add(configured_tts_host)
                    supervisor.register_provider(configured_tts_host, None)

                configured_stt_host = _provider_host(settings.stt_provider)
                if configured_stt_host not in seen_provider_keys:
                    seen_provider_keys.add(configured_stt_host)
                    supervisor.register_provider(configured_stt_host, None)

                if seen_provider_keys:
                    await supervisor.start()
                    GlobalAgentContainer.provider_supervisor = supervisor
                    if smart_llm is not None:
                        if hasattr(smart_llm, "set_provider_supervisor"):
                            smart_llm.set_provider_supervisor(supervisor)
                        else:
                            setattr(smart_llm, "provider_supervisor", supervisor)
                    logger.info(
                        "provider_supervisor_active providers=%s",
                        sorted(seen_provider_keys),
                    )
                else:
                    logger.info("provider_supervisor_skipped reason=no_llm_providers")
            except Exception as supervisor_err:
                logger.warning(f"⚠️ ProviderSupervisor initialization skipped: {supervisor_err}")

            async def _run_boot_probes() -> None:
                try:
                    from core.runtime.startup_health_probes import run_boot_health_probes

                    all_passed, probe_results = await run_boot_health_probes(
                        identity_check=True,
                        memory_check=False,  # Skip - memory may need more time
                        router_check=False,   # Skip - router needs full init
                        tool_check=False,     # Skip - tools loaded on demand
                        stt_check=True,
                        log_check=False,
                    )
                    if not all_passed:
                        logger.error("❌ Critical boot probes failed - continuing with degraded functionality")
                except Exception as e:
                    logger.warning(f"⚠️ Boot health probes failed: {e}")

            if self.mode == MayaRuntimeMode.CONSOLE:
                should_run_console_boot_probes = str(
                    os.getenv("MAYA_CONSOLE_BOOT_PROBES", "0")
                ).strip().lower() in {"1", "true", "yes"}
                if should_run_console_boot_probes:
                    self._start_background_task(_run_boot_probes())
                    logger.info("🏥 Boot health probes scheduled in background for console mode")
                else:
                    logger.info("ℹ️ Boot health probes skipped in console mode")
            else:
                await _run_boot_probes()
        except Exception as e:
            logger.warning(f"⚠️ Global Agent Boot failed ({e}). Falling back to Phase 1 runtime path.")
            self.architecture_phase = 1
            print("⚠️ Phase 2 warm-up failed. Falling back to Phase 1.")

    async def _boot_mode_specific(self, entrypoint_fnc):
        """Strict isolation between Worker and Console paths."""
        mode_str = normalize_intent(self.mode)
        print(f"🚀 Step 3: Starting {mode_str.upper()} Mode...")
        
        if self.mode == MayaRuntimeMode.WORKER:
            await self._boot_worker_mode(entrypoint_fnc)
        else:
            await self._boot_console_mode(entrypoint_fnc)
    async def _boot_console_mode(self, entrypoint_fnc=None):
        """Console mode: Phase 1 direct LLM loop, Phase 2 orchestrator gateway."""
        logger.info(f"🚀 Step 3: Starting CONSOLE Mode (Phase {self.architecture_phase})...")
        console_ingestor_default = "1" if self.architecture_phase >= 6 else "0"
        should_start_console_ingestor = str(
            os.getenv("MAYA_CONSOLE_START_INGESTOR", console_ingestor_default)
        ).strip().lower() in {"1", "true", "yes"}
        if self.architecture_phase >= 2 and should_start_console_ingestor:
            self._start_background_task(self._start_memory_ingestor_task())
        self._print_banner()
        
        # In Phase 1, we skip the Orchestrator/TaskWorker/Ingestor
        # and run a direct input -> LLM -> output loop.
        while True:
            try:
                user_input = input("\n👤 You: ")
                if user_input.lower() in ["exit", "quit"]:
                    logger.info("👋 Exiting console mode.")
                    break
                
                if not user_input.strip():
                    continue
                set_trace_context(
                    trace_id=current_trace_id(),
                    session_id="console_session",
                    user_id="console_user",
                )

                # Import dynamically to avoid circular dependency
                if self.architecture_phase >= 2:
                    from core.runtime.entrypoint import console_entrypoint
                    await console_entrypoint(user_input)
                else:
                    from agent import _handle_console_message
                    await _handle_console_message(user_input)
                
            except KeyboardInterrupt:
                print("\n👋 Goodbye!")
                break
            except EOFError:
                logger.info("👋 Console input closed (EOF). Exiting console mode.")
                break
            except Exception as e:
                logger.error(f"❌ Console Error: {e}")
        
    async def _boot_worker_mode(self, entrypoint_fnc):
        """
        Phase 1 Worker pipeline:
        1. Start token server (for Flutter auth)
        2. Start LiveKit Worker (Blocking)

        Memory ingestor and evaluation loop are Phase 6+ concerns — omitted in Phase 1.
        """
        logger.info(f"🚀 Step 3: Starting WORKER Mode (Phase {self.architecture_phase})...")

        # Start token server only (Flutter needs this for room tokens)
        from api.server import run_token_server
        self._start_background_task(run_token_server())
        # Phase 6+: self._start_background_task(self._start_evaluation_loop())
        self._start_background_task(self._start_memory_ingestor_task())
        self._start_background_task(self._memory_telemetry_loop())

        self._print_banner()

        # Start LiveKit Worker (Blocking)
        if not entrypoint_fnc:
            logger.error("❌ Worker mode requires an entrypoint function.")
            sys.exit(1)

        await self._start_livekit_worker(entrypoint_fnc)

    async def _start_livekit_worker(self, entrypoint_fnc):
        """
        Runs the LiveKit Worker using AgentServer directly.
        Includes infinite retry loop for self-healing.
        """
        from livekit import agents
        from livekit.agents import AgentServer, WorkerOptions
        from utils.schema_fixer import apply_schema_patch

        def _active_livekit_credentials() -> tuple[str | None, str | None, str | None, str]:
            active_slot = str(os.getenv("LIVEKIT_ACTIVE_SLOT", "1") or "1").strip() or "1"
            suffix = "" if active_slot in {"", "1"} else f"_{active_slot}"
            ws_url = (os.getenv(f"LIVEKIT_URL{suffix}") or os.getenv("LIVEKIT_URL") or "").strip() or None
            api_key = (os.getenv(f"LIVEKIT_API_KEY{suffix}") or os.getenv("LIVEKIT_API_KEY") or "").strip() or None
            api_secret = (
                (os.getenv(f"LIVEKIT_API_SECRET{suffix}") or os.getenv("LIVEKIT_API_SECRET") or "").strip()
                or None
            )
            return ws_url, api_key, api_secret, active_slot
        
        async def run_worker_once():
            apply_schema_patch()
            _register_inference_runners()
            
            # Use configured worker port; defaults to 8082.
            port = getattr(settings, "livekit_port", 8082)
            agent_name = getattr(settings, "livekit_agent_name", "maya-one")
            num_idle_processes = max(0, int(os.getenv("LIVEKIT_NUM_IDLE_PROCESSES", "0")))
            job_memory_warn_mb = float(os.getenv("LIVEKIT_JOB_MEMORY_WARN_MB", "1200"))
            job_memory_limit_mb = float(os.getenv("LIVEKIT_JOB_MEMORY_LIMIT_MB", "0"))
            ws_url, api_key, api_secret, active_slot = _active_livekit_credentials()

            if not (ws_url and api_key and api_secret):
                raise RuntimeError(
                    f"Missing LiveKit worker credentials for active slot {active_slot} "
                    f"(ws_url={bool(ws_url)}, api_key={bool(api_key)}, api_secret={bool(api_secret)})"
                )

            options = WorkerOptions(
                entrypoint_fnc=entrypoint_fnc,
                port=port,
                agent_name=agent_name,
                ws_url=ws_url,
                api_key=api_key,
                api_secret=api_secret,
                num_idle_processes=num_idle_processes,
                job_memory_warn_mb=job_memory_warn_mb,
                job_memory_limit_mb=job_memory_limit_mb,
            )
            server = AgentServer.from_server_options(options)

            @server.on("worker_started")
            def on_worker_started(*args):
                logger.info("✅ LiveKit worker connected")
            
            logger.info(
                f"🤖 LiveKit worker connecting... (agent_name={agent_name}, slot={active_slot}, ws={ws_url}, "
                f"idle_processes={num_idle_processes}, mem_warn_mb={job_memory_warn_mb}, mem_limit_mb={job_memory_limit_mb})"
            )
            await server.run()
            logger.warning("⚠️ LiveKit worker disconnected")

        # Retry loop
        while True:
            try:
                await run_worker_once()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.exception("⚠️ Worker crashed. Restarting in 5s...")
                await asyncio.sleep(5)

    async def _memory_telemetry_loop(self) -> None:
        """
        Emit compact process memory telemetry to separate threshold noise from true leaks.
        """
        interval_s = max(10.0, float(os.getenv("LIVEKIT_MEMORY_TELEMETRY_INTERVAL_S", "30")))
        while True:
            try:
                rss_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
                # Linux returns KB, macOS returns bytes.
                rss_mb = (rss_kb / 1024.0) if sys.platform.startswith("linux") else (rss_kb / 1024.0 / 1024.0)
                logger.info(
                    "worker_memory_telemetry rss_mb=%.1f mode=%s background_tasks=%s",
                    rss_mb,
                    self.mode.value,
                    len(self._background_tasks),
                )
                await asyncio.sleep(interval_s)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.warning("worker_memory_telemetry_failed error=%s", e)
                await asyncio.sleep(interval_s)

    async def _start_evaluation_loop(self):
        """Background task for system health monitoring."""
        from telemetry.session_monitor import SessionMonitor
        session_monitor = SessionMonitor()
        logger.info("✅ Evaluation loop started")
        
        while True:
            # Shifted sleep to end of loop to get immediate first log
            try:
                session_monitor.log_system_health()
            except asyncio.CancelledError:
                raise
            except Exception:
                pass
            await asyncio.sleep(60)

    async def _start_memory_ingestor_task(self):
        """Ensure memory ingestor is running."""
        if not GlobalAgentContainer.memory_ingestor:
            logger.warning("⚠️ Memory ingestor unavailable on GlobalAgentContainer")
            return

        self.memory_ingestor = GlobalAgentContainer.memory_ingestor
        try:
            if hasattr(self.memory_ingestor, "index_existing_files"):
                await asyncio.to_thread(self.memory_ingestor.index_existing_files)
            if hasattr(self.memory_ingestor, "start"):
                await self.memory_ingestor.start()
            logger.info("✅ Memory ingestor started")
        except Exception as e:
            logger.error("❌ Memory ingestor failed to start: %s", e, exc_info=True)

    async def _start_memory_ingestor(self):
        # Deprecated: alias for compatibility if needed, but we use _start_memory_ingestor_task now
        await self._start_memory_ingestor_task()


    def _print_banner(self):
        """Final READY signal."""
        mode_str = normalize_intent(self.mode)
        print("\n" + "="*40)
        print("🚀 MAYA RUNTIME READY")
        print(f"Mode: {mode_str.upper()}")
        print(f"Environment: {os.getenv('ENVIRONMENT', 'development')}")
        print(f"Port 5050: {'ACTIVE' if self.mode == MayaRuntimeMode.WORKER else 'OFF'}")
        print(f"Evaluation: ACTIVE")
        print("="*40 + "\n")

def detect_runtime_mode() -> MayaRuntimeMode:
    """Detection logic: prefers CLI arg, falls back to env."""
    args = sys.argv
    if "console" in args:
        return MayaRuntimeMode.CONSOLE
    
    env_mode = os.getenv("AGENT_MODE", "").lower()
    if env_mode == "console":
        return MayaRuntimeMode.CONSOLE
        
    return MayaRuntimeMode.WORKER
