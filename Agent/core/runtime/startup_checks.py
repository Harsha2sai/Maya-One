import socket
import logging
import os
from dataclasses import dataclass
from typing import Dict
from config.settings import settings

logger = logging.getLogger(__name__)


@dataclass
class StartupReadinessReport:
    handoff: bool
    persistence: bool
    message_bus: bool
    progress_bridge: bool
    skill_policy: bool
    degraded: bool
    reasons: Dict[str, str]

def check_port_free(port):
    """Check if a port is free by trying to bind to it."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("0.0.0.0", port))
        return True
    except OSError:
        return False
    finally:
        s.close()

def validate_voice_plugins():
    """Checks for necessary LiveKit plugins."""
    from importlib.util import find_spec
    plugins = [
        ("livekit.plugins.deepgram", "deepgram"),
        ("livekit.plugins.silero", "silero"),
        ("livekit.plugins.openai", "openai"),
        ("livekit.plugins.cartesia", "cartesia")
    ]
    
    missing = []
    for spec_name, p_name in plugins:
        if find_spec(spec_name) is None:
            missing.append(p_name)
    
    if missing:
        logger.warning(f"⚠️ Missing voice plugins: {missing}. Some functionality may fail.")


def run_prerequisite_matrix() -> StartupReadinessReport:
    reasons: Dict[str, str] = {}
    handoff_ok = False
    persistence_ok = False
    message_bus_ok = False
    progress_bridge_ok = False
    skill_policy_ok = True

    try:
        from core.agents.handoff_manager import HandoffManager

        handoff_ok = bool(getattr(HandoffManager, "MAX_DEPTH_STAGE_A", 0) >= 2)
        if not handoff_ok:
            reasons["handoff"] = "MAX_DEPTH_STAGE_A is below required depth=2"
    except Exception as exc:
        reasons["handoff"] = f"import_failed:{exc}"

    try:
        from core.tasks.task_persistence import TaskPersistence

        persistence_ok = TaskPersistence is not None
    except Exception as exc:
        reasons["persistence"] = f"import_failed:{exc}"

    try:
        from core.messaging.message_bus import MessageBus

        message_bus_ok = MessageBus is not None
    except Exception as exc:
        reasons["message_bus"] = f"import_failed:{exc}"

    try:
        from core.messaging.progress_stream import ProgressStream

        progress_bridge_ok = ProgressStream is not None
    except Exception as exc:
        reasons["progress_bridge"] = f"import_failed:{exc}"

    # Skill policy hardening in this slice is gated by explicit enable flags.
    if bool(getattr(settings, "multi_agent_features_enabled", False)):
        if not bool(getattr(settings, "max_consecutive_failures", 0)):
            skill_policy_ok = False
            reasons["skill_policy"] = "policy defaults not loaded"

    degraded = False
    required_ok = handoff_ok and persistence_ok and message_bus_ok and progress_bridge_ok and skill_policy_ok
    if bool(getattr(settings, "multi_agent_features_enabled", False)) and not required_ok:
        degraded = True
        settings.multi_agent_features_enabled = False
        os.environ["MULTI_AGENT_RUNTIME_DEGRADED"] = "1"

    report = StartupReadinessReport(
        handoff=handoff_ok,
        persistence=persistence_ok,
        message_bus=message_bus_ok,
        progress_bridge=progress_bridge_ok,
        skill_policy=skill_policy_ok,
        degraded=degraded,
        reasons=reasons,
    )
    logger.info(
        "multi_agent_readiness handoff=%s persistence=%s message_bus=%s progress_bridge=%s "
        "skill_policy=%s degraded=%s reasons=%s",
        report.handoff,
        report.persistence,
        report.message_bus,
        report.progress_bridge,
        report.skill_policy,
        report.degraded,
        report.reasons,
    )
    return report

def run_startup_checks(*, require_runtime_ports: bool = True):
    """
    Final production pre-flight checks.
    Ensures ports are available and critical plugins are present.
    """
    logger.info("🏥 Running Production Startup Checks...")

    if require_runtime_ports:
        worker_port = getattr(settings, "livekit_port", 8082)

        # Worker mode requires token server and LiveKit worker ports.
        assert check_port_free(5050), "Port 5050 (Token Server) still busy"
        assert check_port_free(worker_port), f"Port {worker_port} (LiveKit Worker HTTP) still busy"
    else:
        logger.info("ℹ️ Skipping worker runtime port checks for console mode")

    # Check Plugins
    validate_voice_plugins()
    run_prerequisite_matrix()
    
    logger.info("✅ Startup checks passed")
